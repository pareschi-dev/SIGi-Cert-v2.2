from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader, PdfWriter
from pydantic import BaseModel, Field, field_validator, model_validator

from certhub.core.validators import validate_cnpj, validate_cpf
from certhub.config import (
    BASE_DIR,
    create_consultation_directory,
    downloads_directory,
    find_consultation_directory,
    load_certidoes_config,
    resolve_project_path,
)
from certhub.site_automation import SITE_FLOWS, _safe_error_detail, run_site

MANUAL_CAPTCHA_SITE_CODES = frozenset(("cndt", "ceis_cgu", "cartao_cnpj"))
MANUAL_ONLY_SITE_CODES = MANUAL_CAPTCHA_SITE_CODES | {"sicaf"}
MANUAL_FALLBACK_SITE_CODES = frozenset(("simples_nacional",))
MANUAL_PDF_FILE_IDS = {
    "cndt": "cndt",
    "ceis_cgu": "cgu_certidoes",
    "cartao_cnpj": "receita_cnpj_comprovante",
    "sicaf": "compras_gov",
    "simples_nacional": "simples_nacional",
}

SITE_CATALOG = [
    {"codigo": "sicaf", "nome": "SICAF — Compras.gov.br", "orgao": "Compras.gov.br", "captcha": "Certificado digital/token", "url": "https://www3.comprasnet.gov.br/sicaf-web/index.jsf"},
    {"codigo": "receita_inss_cnpj", "nome": "Certidão de Pessoa Jurídica (CNPJ)", "orgao": "Receita Federal", "captcha": "Desafio assistido se aparecer", "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj#"},
    {"codigo": "receita_inss_cpf", "nome": "Certidão de Pessoa Física (CPF)", "orgao": "Receita Federal", "captcha": "Desafio assistido se aparecer", "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cpf#"},
    {"codigo": "fgts", "nome": "Certificado de Regularidade do FGTS (CRF)", "orgao": "Caixa Econômica Federal", "captcha": "Sem CAPTCHA esperado", "url": "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"},
    {"codigo": "cndt", "nome": "Certidão Negativa de Débitos Trabalhistas (CNDT)", "orgao": "Tribunal Superior do Trabalho", "captcha": "CAPTCHA assistido, se solicitado", "url": "https://cndt-certidao.tst.jus.br/"},
    {"codigo": "inelegibilidade_cnj", "nome": "Cadastro Nacional de Condenações Cíveis por Ato de Improbidade Administrativa e Inelegibilidade", "orgao": "Conselho Nacional de Justiça", "captcha": "Desafio assistido, se solicitado", "url": "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php?validar=form"},
    {"codigo": "ceis_cgu", "nome": "Sistema de Certidões da Controladoria-Geral da União", "orgao": "Controladoria-Geral da União", "captcha": "reCAPTCHA assistido, se solicitado", "url": "https://certidoes.cgu.gov.br/"},
    {"codigo": "cartao_cnpj", "nome": "Comprovante de Inscrição e de Situação Cadastral (CNPJ)", "orgao": "Receita Federal", "captcha": "hCaptcha assistido, se solicitado", "url": "https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/"},
    {"codigo": "tcu_inidoneos", "nome": "Certidão de Licitantes Inidôneos (TCU)", "orgao": "Tribunal de Contas da União", "captcha": "Desafio assistido, se solicitado", "url": "https://certidoes.apps.tcu.gov.br/emitir-certidao-inidoneos"},
    {"codigo": "simples_nacional", "nome": "Consulta Optantes pelo Simples Nacional", "orgao": "Receita Federal", "captcha": "Desafio assistido se aparecer", "url": "https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21"},
]
for site in SITE_CATALOG:
    flow = SITE_FLOWS.get(site["codigo"])
    if flow is not None:
        site["url"] = flow["url"]
_CONFIGURED_PORTALS = load_certidoes_config().get("portais", [])
_CONFIG_ID_TO_SITE_CODE = {
    "compras_gov": "sicaf",
    "receita_cnpj": "receita_inss_cnpj",
    "receita_cpf": "receita_inss_cpf",
    "fgts_crf": "fgts",
    "cndt": "cndt",
    "cnj_improbidade": "inelegibilidade_cnj",
    "cgu_certidoes": "ceis_cgu",
    "receita_cnpj_comprovante": "cartao_cnpj",
    "tcu_licitantes": "tcu_inidoneos",
    "simples_nacional": "simples_nacional",
}
_PORTAL_CONFIG_BY_CODE = {
    _CONFIG_ID_TO_SITE_CODE[portal.get("id")]: portal
    for portal in _CONFIGURED_PORTALS
    if isinstance(portal, dict) and portal.get("id") in _CONFIG_ID_TO_SITE_CODE
}
for portal in _CONFIGURED_PORTALS if isinstance(_CONFIGURED_PORTALS, list) else []:
    if not isinstance(portal, dict):
        continue
    site_code = _CONFIG_ID_TO_SITE_CODE.get(portal.get("id"), portal.get("id"))
    site = next((item for item in SITE_CATALOG if item["codigo"] == site_code), None)
    if site is None:
        continue
    site["url"] = portal.get("url_servico") or portal.get("url_inicial") or site["url"]
    site["captcha"] = portal.get("captcha") or site["captcha"]
SITE_EXECUTION_MODES = {
    site_code: config.get("modo", "INTERNO")
    for site_code, config in _PORTAL_CONFIG_BY_CODE.items()
}
SITE_CODES = {site["codigo"] for site in SITE_CATALOG}
IMPLEMENTED_SITE_CODES = {
    site_code
    for site_code, config in _PORTAL_CONFIG_BY_CODE.items()
    if config.get("implementado") is True
    and site_code in SITE_FLOWS
    and site_code not in MANUAL_ONLY_SITE_CODES
}
SITE_DOCUMENT_TYPES = {
    "sicaf": {"CNPJ"},
    "receita_inss_cnpj": {"CNPJ"},
    "receita_inss_cpf": {"CPF"},
    "fgts": {"CNPJ"},
    "cndt": {"CPF", "CNPJ"},
    "inelegibilidade_cnj": {"CPF", "CNPJ"},
    "ceis_cgu": {"CPF", "CNPJ"},
    "cartao_cnpj": {"CNPJ"},
    "tcu_inidoneos": {"CPF", "CNPJ"},
    "simples_nacional": {"CNPJ"},
}
PROJECT_DIR = BASE_DIR
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
# Keep three workers so the CNPJ CAPTCHA portals can prepare their visible tabs
# together; other visible flows are serialized by run_site's browser condition.
MAX_CONCURRENT_SITE_TASKS = 3
PRIORITY_CNPJ_CAPTCHA_SITES = ("cndt", "ceis_cgu", "cartao_cnpj")
SITE_EXECUTOR = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_SITE_TASKS,
    thread_name_prefix="certhub-site",
)
CAPTCHA_LOCK = threading.Lock()
PENDING_CAPTCHAS: dict[str, dict] = {}
OUTPUT_ROOT = downloads_directory()
INITIALIZED_DATABASES: set[str] = set()
DATABASE_INIT_LOCK = threading.Lock()


def _database_path() -> Path:
    return resolve_project_path(os.getenv("CERTHUB_DB_PATH", "data/consultas_demo.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    database_key = str(path.resolve())
    if database_key in INITIALIZED_DATABASES:
        return connection
    with DATABASE_INIT_LOCK:
        if database_key in INITIALIZED_DATABASES:
            return connection
        connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS consultas (
            id TEXT PRIMARY KEY,
            documento_tipo TEXT NOT NULL,
            documento_hash TEXT NOT NULL,
            documento_mascarado TEXT NOT NULL,
            status TEXT NOT NULL,
            iniciado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consulta_sites (
            id TEXT PRIMARY KEY,
            consulta_id TEXT NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            site_codigo TEXT NOT NULL,
            status TEXT NOT NULL,
            resultado TEXT
        );
        CREATE TABLE IF NOT EXISTS consulta_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consulta_id TEXT NOT NULL,
            acao TEXT NOT NULL,
            documento_mascarado TEXT NOT NULL,
            sites_consultados TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            hash_anterior TEXT,
            registro_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS captchas_pendentes (
            id TEXT PRIMARY KEY,
            consulta_id TEXT NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            site_codigo TEXT NOT NULL,
            tipo TEXT NOT NULL,
            imagem_base64 TEXT,
            campo_selector TEXT,
            status TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            criado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consulta_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consulta_id TEXT NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            evento TEXT NOT NULL,
            payload TEXT NOT NULL,
            criado_em TEXT NOT NULL
        );
        """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(consultas)")}
        if "finalidade" in columns:
            connection.execute("ALTER TABLE consultas DROP COLUMN finalidade")
        INITIALIZED_DATABASES.add(database_key)
    return connection


def _mask_document(document_type: str, digits: str) -> str:
    if document_type == "CPF":
        return f"***.***.***-{digits[-2:]}"
    return f"**.***.***/****-{digits[-2:]}"


class ConsultationRequest(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    tipo: Literal["CPF", "CNPJ"]
    sites: list[str] = Field(min_length=1, max_length=10)
    data_nascimento: str | None = Field(default=None, max_length=10)
    consulta_id: str | None = Field(default=None, max_length=64)

    @field_validator("documento", mode="before")
    @classmethod
    def trim_document(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not re.fullmatch(r"[0-9./\-\s]+", value):
                raise ValueError("Informe apenas os dígitos e a formatação do CPF/CNPJ.")
        return value

    @field_validator("sites")
    @classmethod
    def sites_must_be_known_and_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("A lista de sites contém duplicatas.")
        unknown = set(value) - SITE_CODES
        if unknown:
            raise ValueError(f"Sites não reconhecidos: {', '.join(sorted(unknown))}")
        return value

    @model_validator(mode="after")
    def sites_must_support_document_type(self):
        not_implemented = [site for site in self.sites if site not in IMPLEMENTED_SITE_CODES]
        if not_implemented:
            raise ValueError(f"Macros ainda não implementados: {', '.join(not_implemented)}")
        unsupported = [site for site in self.sites if self.tipo not in SITE_DOCUMENT_TYPES[site]]
        if unsupported:
            raise ValueError(f"Estes portais não aceitam {self.tipo}: {', '.join(unsupported)}")
        if "receita_inss_cpf" in self.sites and not self.data_nascimento:
            raise ValueError("Informe a data de nascimento para consultar a Receita CPF.")
        if self.data_nascimento:
            try:
                datetime.strptime(self.data_nascimento, "%Y-%m-%d")
            except ValueError as error:
                raise ValueError("Data de nascimento inválida; use AAAA-MM-DD.") from error
        return self

    def normalized_document(self) -> str:
        digits = re.sub(r"\D", "", self.documento)
        is_valid = validate_cpf(digits) if self.tipo == "CPF" else validate_cnpj(digits)
        expected_length = 11 if self.tipo == "CPF" else 14
        if len(digits) != expected_length or not is_valid:
            raise HTTPException(status_code=422, detail=f"{self.tipo} inválido.")
        return digits


class CaptchaResolution(BaseModel):
    resposta: str = Field(min_length=1, max_length=512)


class MergePdfsRequest(BaseModel):
    arquivos: list[str] = Field(min_length=1, max_length=50)

    @field_validator("arquivos")
    @classmethod
    def filenames_must_be_unique_pdf_names(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("A ordem contém nomes de arquivo duplicados.")
        if any(Path(name).name != name or Path(name).suffix.lower() != ".pdf" for name in value):
            raise ValueError("Informe somente nomes de arquivos PDF, sem caminhos.")
        return value


class ManualPortalRequest(BaseModel):
    documento: str = Field(min_length=1, max_length=32)
    tipo: Literal["CPF", "CNPJ"]
    site: str
    consulta_id: str | None = Field(default=None, max_length=64)

    @field_validator("documento", mode="before")
    @classmethod
    def trim_document(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not re.fullmatch(r"[0-9./\-\s]+", value):
                raise ValueError("Informe apenas os dígitos e a formatação do CPF/CNPJ.")
        return value

    @field_validator("site")
    @classmethod
    def require_manual_portal(cls, value: str) -> str:
        if value not in MANUAL_ONLY_SITE_CODES | MANUAL_FALLBACK_SITE_CODES:
            raise ValueError("Este portal não está configurado para abertura manual.")
        return value

    @model_validator(mode="after")
    def validate_document(self):
        digits = re.sub(r"\D", "", self.documento)
        valid = validate_cpf(digits) if self.tipo == "CPF" else validate_cnpj(digits)
        expected_length = 11 if self.tipo == "CPF" else 14
        if len(digits) != expected_length or not valid:
            raise ValueError(f"{self.tipo} inválido.")
        if self.tipo not in SITE_DOCUMENT_TYPES[self.site]:
            raise ValueError(f"O portal {self.site} não aceita {self.tipo}.")
        return self

    def normalized_document(self) -> str:
        return re.sub(r"\D", "", self.documento)


app = FastAPI(title="SIG-ES | Certidões", version="0.1.0")


@app.get("/", include_in_schema=False)
def home():
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={"detail": "Frontend ainda não compilado. Execute npm install e npm run build na pasta frontend."},
        )
    return FileResponse(index_file)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/api/v1/sites/catalogo")
def site_catalog():
    return {
        "sites": [
            {
                **site,
                "execution_mode": "MANUAL" if site["codigo"] in MANUAL_CAPTCHA_SITE_CODES else SITE_EXECUTION_MODES[site["codigo"]],
                "integration_configured": site["codigo"] in IMPLEMENTED_SITE_CODES,
                "manual_only": site["codigo"] in MANUAL_ONLY_SITE_CODES,
                "manual_mode": "captcha" if site["codigo"] in MANUAL_CAPTCHA_SITE_CODES else "token" if site["codigo"] == "sicaf" else None,
                "document_types": sorted(SITE_DOCUMENT_TYPES[site["codigo"]]),
            }
            for site in SITE_CATALOG
        ]
    }


def _record_event(connection: sqlite3.Connection, consultation_id: str, event: str, payload: dict) -> None:
    connection.execute(
        "INSERT INTO consulta_eventos (consulta_id, evento, payload, criado_em) VALUES (?, ?, ?, ?)",
        (consultation_id, event, json.dumps(payload, ensure_ascii=False), datetime.now(UTC).isoformat(timespec="seconds")),
    )


def _set_site_status(consultation_id: str, site_code: str, status: str, result: dict | None) -> None:
    event_name = {
        "rodando": "site_iniciado",
        "sucesso": "site_concluido",
        "erro": "site_erro",
        "aguardando_captcha": "site_status",
    }.get(status, "site_status")
    stored_result = dict(result) if result is not None else None
    if stored_result is not None:
        stored_result.pop("pdf_path", None)
    with closing(_connect()) as connection, connection:
        connection.execute(
            "UPDATE consulta_sites SET status = ?, resultado = ? WHERE consulta_id = ? AND site_codigo = ?",
            (status, json.dumps(stored_result, ensure_ascii=False) if stored_result is not None else None, consultation_id, site_code),
        )
        rows = connection.execute(
            "SELECT status FROM consulta_sites WHERE consulta_id = ?", (consultation_id,)
        ).fetchall()
        statuses = [row["status"] for row in rows]
        if statuses and all(state in {"sucesso", "erro", "cancelada"} for state in statuses):
            overall = "concluida" if "sucesso" in statuses else "erro"
        elif "aguardando_captcha" in statuses:
            overall = "aguardando_captcha"
        else:
            overall = "em_andamento"
        connection.execute("UPDATE consultas SET status = ? WHERE id = ?", (overall, consultation_id))
        _record_event(connection, consultation_id, event_name, {"site_codigo": site_code, "status": status, "resultado": stored_result})


def _wait_for_human_captcha(
    consultation_id: str,
    site_code: str,
    captcha_type: str,
    image_base64: str | None,
    input_selector: str | None,
) -> str | None:
    captcha_id = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    gate = {"event": threading.Event(), "answer": None}
    with CAPTCHA_LOCK:
        PENDING_CAPTCHAS[captcha_id] = gate
    with closing(_connect()) as connection, connection:
        connection.execute(
            "INSERT INTO captchas_pendentes (id, consulta_id, site_codigo, tipo, imagem_base64, campo_selector, status, expira_em, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (captcha_id, consultation_id, site_code, captcha_type, image_base64, input_selector, "aguardando", expires_at.isoformat(), datetime.now(UTC).isoformat()),
        )
        connection.execute("UPDATE consulta_sites SET status = 'aguardando_captcha' WHERE consulta_id = ? AND site_codigo = ?", (consultation_id, site_code))
        connection.execute("UPDATE consultas SET status = 'aguardando_captcha' WHERE id = ?", (consultation_id,))
        _record_event(connection, consultation_id, "captcha_necessario", {
            "captcha_id": captcha_id,
            "site_codigo": site_code,
            "tipo": captcha_type,
            "imagem_base64": image_base64,
            "mensagem": (
                "Autentique com certificado digital/token e navegue até a certidão para impressão."
                if captcha_type == "token"
                else "O CNPJ já está preenchido na aba do TST. Resolva o CAPTCHA, clique em Emitir Certidão e aguarde o download começar; depois confirme aqui. O sistema não preencherá o CAPTCHA nem clicará no botão."
                if site_code == "cndt"
                else "O CNPJ já está preenchido na aba oficial deste portal. Resolva o CAPTCHA manualmente e confirme aqui para continuar."
            ),
            "expira_em": expires_at.isoformat(),
        })

    answered = gate["event"].wait(timeout=300)
    with CAPTCHA_LOCK:
        PENDING_CAPTCHAS.pop(captcha_id, None)
    with closing(_connect()) as connection, connection:
        connection.execute(
            "UPDATE captchas_pendentes SET status = ? WHERE id = ?",
            ("respondido" if answered else "expirado", captcha_id),
        )
    return gate["answer"] if answered else None


def _run_site_task(
    consultation_id: str,
    site_code: str,
    document: str,
    target_directory: str,
    additional_data: dict | None = None,
) -> None:
    try:
        result = run_site(
            consultation_id,
            site_code,
            document,
            lambda code, status, detail: _set_site_status(consultation_id, code, status, {"detalhe": detail} if detail else None),
            lambda code, kind, image, selector: _wait_for_human_captcha(
                consultation_id, code, kind, image, selector
            ),
            Path(target_directory),
            additional_data=additional_data,
        )
    except Exception as error:
        _set_site_status(consultation_id, site_code, "erro", {"erro": _safe_error_detail(error)})
    else:
        _set_site_status(consultation_id, site_code, "sucesso", result)


def _serialize_consultation(connection: sqlite3.Connection, consultation_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM consultas WHERE id = ?", (consultation_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    site_rows = connection.execute(
        "SELECT site_codigo, status, resultado FROM consulta_sites WHERE consulta_id = ? ORDER BY rowid",
        (consultation_id,),
    ).fetchall()
    consultation_directory = find_consultation_directory(
        row["documento_hash"], row["iniciado_em"], OUTPUT_ROOT
    )
    pdf_files = []
    if consultation_directory is not None:
        for pdf_path in sorted(consultation_directory.glob("*.pdf"), key=lambda item: item.name.casefold()):
            try:
                if not pdf_path.is_file():
                    continue
                file_bytes = pdf_path.read_bytes()
                pdf_files.append({
                    "nome": pdf_path.name,
                    "tamanho": len(file_bytes),
                    "valido": file_bytes.startswith(b"%PDF-") and len(file_bytes) >= 8,
                    "sha256": hashlib.sha256(file_bytes).hexdigest(),
                    "modificado_em": datetime.fromtimestamp(
                        pdf_path.stat().st_mtime, UTC
                    ).isoformat(timespec="seconds"),
                })
            except OSError:
                continue
    serialized_sites = []
    manual_completion_recorded = False
    for item in site_rows:
        result = json.loads(item["resultado"]) if item["resultado"] else None
        site_status = item["status"]
        if (
            site_status == "aguardando_manual"
            and item["site_codigo"] in MANUAL_PDF_FILE_IDS
            and consultation_directory is not None
        ):
            manual_pdf = consultation_directory / f"{MANUAL_PDF_FILE_IDS[item['site_codigo']]}.pdf"
            try:
                reader = PdfReader(str(manual_pdf), strict=True)
                if not reader.is_encrypted and len(reader.pages) > 0:
                    manual_pdf_bytes = manual_pdf.read_bytes()
                    if manual_pdf_bytes.startswith(b"%PDF-"):
                        result = {
                            "arquivo": manual_pdf.name,
                            "pdf_sha256": hashlib.sha256(manual_pdf_bytes).hexdigest(),
                            "detalhe": "PDF manual salvo e validado na pasta da sessão.",
                        }
                        connection.execute(
                            "UPDATE consulta_sites SET status = 'sucesso', resultado = ? "
                            "WHERE consulta_id = ? AND site_codigo = ? AND status = 'aguardando_manual'",
                            (json.dumps(result, ensure_ascii=False), consultation_id, item["site_codigo"]),
                        )
                        _record_event(connection, consultation_id, "site_concluido", {
                            "site_codigo": item["site_codigo"], "status": "sucesso", "resultado": result,
                        })
                        site_status = "sucesso"
                        manual_completion_recorded = True
            except Exception:
                # Keep the manual job pending until the expected file is a readable PDF.
                pass
        if result is not None:
            result.pop("pdf_path", None)
            if consultation_directory is not None and site_status == "sucesso":
                flow_code = {
                    "receita_inss_cnpj": "receita_inss_cnpj",
                    "receita_inss_cpf": "receita_inss_cpf",
                    "fgts": "fgts",
                    "inelegibilidade_cnj": "inelegibilidade_cnj",
                }.get(item["site_codigo"], item["site_codigo"])
                flow = SITE_FLOWS.get(flow_code, {})
                pdf_path = consultation_directory / f"{flow.get('file_id', flow_code)}.pdf"
                if pdf_path.is_file():
                    result["pdf_path"] = str(pdf_path.resolve())
        serialized_sites.append({
            "codigo": item["site_codigo"],
            "status": site_status,
            "resultado": result,
        })
    if manual_completion_recorded:
        statuses = [item["status"] for item in connection.execute(
            "SELECT status FROM consulta_sites WHERE consulta_id = ?", (consultation_id,)
        ).fetchall()]
        overall = "concluida" if statuses and all(state in {"sucesso", "erro", "cancelada"} for state in statuses) else "em_andamento"
        connection.execute("UPDATE consultas SET status = ? WHERE id = ?", (overall, consultation_id))
        _record_event(connection, consultation_id, "consulta_atualizada", {"status": overall})
        connection.commit()
        current_status = overall
    else:
        current_status = row["status"]
    return {
        "id": row["id"],
        "documento_tipo": row["documento_tipo"],
        "documento_mascarado": row["documento_mascarado"],
        "status": current_status,
        "iniciado_em": row["iniciado_em"],
        "pasta_disponivel": consultation_directory is not None,
        "pasta_destino": str(consultation_directory.resolve()) if consultation_directory else None,
        "arquivos_pdf": pdf_files,
        "sites": serialized_sites,
        "resultados_consolidados": [
            {"site_codigo": item["codigo"], **item["resultado"]}
            for item in serialized_sites
            if item["status"] == "sucesso" and item["resultado"]
        ],
    }


@app.post("/api/v1/consultas", status_code=202)
def create_consultation(request: ConsultationRequest):
    digits = request.normalized_document()
    masked = _mask_document(request.tipo, digits)
    document_hash = hashlib.sha256(digits.encode("ascii")).hexdigest()
    consultation_id = request.consulta_id
    if consultation_id:
        with closing(_connect()) as connection, connection:
            existing = connection.execute(
                "SELECT documento_tipo, documento_hash, iniciado_em FROM consultas WHERE id = ?",
                (consultation_id,),
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Consulta ativa não encontrada.")
            if existing["documento_tipo"] != request.tipo or existing["documento_hash"] != document_hash:
                raise HTTPException(status_code=409, detail="A pasta ativa pertence a outro documento.")
            consultation_directory = find_consultation_directory(
                existing["documento_hash"], existing["iniciado_em"], OUTPUT_ROOT
            )
            if consultation_directory is None:
                raise HTTPException(status_code=404, detail="Pasta da consulta ativa não encontrada.")
            current_sites = {
                row["site_codigo"]: row["status"]
                for row in connection.execute(
                    "SELECT site_codigo, status FROM consulta_sites WHERE consulta_id = ?",
                    (consultation_id,),
                ).fetchall()
            }
            duplicates = [
                code for code in request.sites
                if code in current_sites and current_sites[code] != "erro"
            ]
            if duplicates:
                raise HTTPException(
                    status_code=409,
                    detail=f"Já existe uma execução para: {', '.join(duplicates)}.",
                )
            for site_code in request.sites:
                if site_code in current_sites:
                    connection.execute(
                        "UPDATE consulta_sites SET status = 'pendente', resultado = NULL "
                        "WHERE consulta_id = ? AND site_codigo = ?",
                        (consultation_id, site_code),
                    )
                else:
                    connection.execute(
                        "INSERT INTO consulta_sites (id, consulta_id, site_codigo, status) VALUES (?, ?, ?, 'pendente')",
                        (str(uuid.uuid4()), consultation_id, site_code),
                    )
            connection.execute(
                "UPDATE consultas SET status = 'em_andamento' WHERE id = ?",
                (consultation_id,),
            )
            _record_event(connection, consultation_id, "sites_adicionados", {
                "sites": request.sites, "documento_mascarado": masked,
            })
            timestamp = datetime.now(UTC).isoformat(timespec="seconds")
            previous_audit = connection.execute(
                "SELECT registro_hash FROM consulta_auditoria ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous = previous_audit["registro_hash"] if previous_audit else None
            audit_payload = json.dumps(
                [consultation_id, "sites_adicionados", masked, request.sites, timestamp, previous],
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO consulta_auditoria (consulta_id, acao, documento_mascarado, sites_consultados, timestamp, hash_anterior, registro_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    consultation_id,
                    "sites_adicionados",
                    masked,
                    json.dumps(request.sites),
                    timestamp,
                    previous,
                    hashlib.sha256(audit_payload.encode("utf-8")).hexdigest(),
                ),
            )
            consultation = _serialize_consultation(connection, consultation_id)
    else:
        consultation_id = str(uuid.uuid4())
        consultation_directory, started_at_value = create_consultation_directory(digits, OUTPUT_ROOT)
        started_at = started_at_value.isoformat(timespec="seconds")
        with closing(_connect()) as connection, connection:
            last_audit = connection.execute(
                "SELECT registro_hash FROM consulta_auditoria ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous = last_audit["registro_hash"] if last_audit else None
            connection.execute(
                "INSERT INTO consultas (id, documento_tipo, documento_hash, documento_mascarado, status, iniciado_em) VALUES (?, ?, ?, ?, ?, ?)",
                (consultation_id, request.tipo, document_hash, masked, "em_andamento", started_at),
            )
            connection.executemany(
                "INSERT INTO consulta_sites (id, consulta_id, site_codigo, status) VALUES (?, ?, ?, ?)",
                [(str(uuid.uuid4()), consultation_id, code, "pendente") for code in request.sites],
            )
            _record_event(connection, consultation_id, "consulta_iniciada", {
                "sites": request.sites, "documento_mascarado": masked,
            })
            audit_payload = json.dumps(
                [consultation_id, "iniciada", masked, request.sites, started_at, previous],
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO consulta_auditoria (consulta_id, acao, documento_mascarado, sites_consultados, timestamp, hash_anterior, registro_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    consultation_id,
                    "iniciada",
                    masked,
                    json.dumps(request.sites),
                    started_at,
                    previous,
                    hashlib.sha256(audit_payload.encode("utf-8")).hexdigest(),
                ),
            )
            consultation = _serialize_consultation(connection, consultation_id)
    priority_sites = [code for code in PRIORITY_CNPJ_CAPTCHA_SITES if code in request.sites and request.tipo == "CNPJ"]
    ordered_sites = [*priority_sites, *(code for code in request.sites if code not in priority_sites)]
    for site_code in ordered_sites:
        SITE_EXECUTOR.submit(
            _run_site_task,
            consultation_id,
            site_code,
            digits,
            str(consultation_directory),
            {"data_nascimento": request.data_nascimento, "tipo": request.tipo},
        )
    return {
        "consulta_id": consultation_id,
        "status": consultation["status"],
        "consulta": consultation,
        "pasta_destino": str(consultation_directory.resolve()),
    }


@app.post("/api/v1/consultas/manual", status_code=201)
def create_manual_portal_session(request: ManualPortalRequest):
    digits = request.normalized_document()
    masked = _mask_document(request.tipo, digits)
    document_hash = hashlib.sha256(digits.encode("ascii")).hexdigest()
    consultation_id = request.consulta_id
    if consultation_id:
        with closing(_connect()) as connection, connection:
            existing = connection.execute(
                "SELECT documento_tipo, documento_hash, iniciado_em FROM consultas WHERE id = ?",
                (consultation_id,),
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Consulta ativa não encontrada.")
            if existing["documento_tipo"] != request.tipo or existing["documento_hash"] != document_hash:
                raise HTTPException(status_code=409, detail="A pasta ativa pertence a outro documento.")
            consultation_directory = find_consultation_directory(
                existing["documento_hash"], existing["iniciado_em"], OUTPUT_ROOT
            )
            if consultation_directory is None:
                raise HTTPException(status_code=404, detail="Pasta da consulta ativa não encontrada.")

            existing_site = connection.execute(
                "SELECT status FROM consulta_sites WHERE consulta_id = ? AND site_codigo = ?",
                (consultation_id, request.site),
            ).fetchone()
            if existing_site is not None and existing_site["status"] == "sucesso":
                raise HTTPException(status_code=409, detail="Este portal já foi concluído nesta consulta.")
            if existing_site is None:
                connection.execute(
                    "INSERT INTO consulta_sites (id, consulta_id, site_codigo, status) VALUES (?, ?, ?, 'aguardando_manual')",
                    (str(uuid.uuid4()), consultation_id, request.site),
                )
            else:
                connection.execute(
                    "UPDATE consulta_sites SET status = 'aguardando_manual', resultado = NULL "
                    "WHERE consulta_id = ? AND site_codigo = ?",
                    (consultation_id, request.site),
                )
            connection.execute(
                "UPDATE consultas SET status = 'aguardando_manual' WHERE id = ?",
                (consultation_id,),
            )
            _record_event(connection, consultation_id, "site_status", {
                "site_codigo": request.site,
                "status": "aguardando_manual",
                "detalhe": "Portal manual adicionado à pasta ativa da consulta.",
            })
            timestamp = datetime.now(UTC).isoformat(timespec="seconds")
            previous_audit = connection.execute(
                "SELECT registro_hash FROM consulta_auditoria ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous = previous_audit["registro_hash"] if previous_audit else None
            audit_payload = json.dumps(
                [consultation_id, "portal_manual_anexado", masked, request.site, timestamp, previous],
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO consulta_auditoria (consulta_id, acao, documento_mascarado, sites_consultados, timestamp, hash_anterior, registro_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    consultation_id,
                    "portal_manual_anexado",
                    masked,
                    json.dumps([request.site]),
                    timestamp,
                    previous,
                    hashlib.sha256(audit_payload.encode("utf-8")).hexdigest(),
                ),
            )
            consultation = _serialize_consultation(connection, consultation_id)
    else:
        consultation_id = str(uuid.uuid4())
        consultation_directory, started_at_value = create_consultation_directory(digits, OUTPUT_ROOT)
        started_at = started_at_value.isoformat(timespec="seconds")
        with closing(_connect()) as connection, connection:
            last_audit = connection.execute(
                "SELECT registro_hash FROM consulta_auditoria ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous = last_audit["registro_hash"] if last_audit else None
            connection.execute(
                "INSERT INTO consultas (id, documento_tipo, documento_hash, documento_mascarado, status, iniciado_em) VALUES (?, ?, ?, ?, ?, ?)",
                (consultation_id, request.tipo, document_hash, masked, "aguardando_manual", started_at),
            )
            connection.execute(
                "INSERT INTO consulta_sites (id, consulta_id, site_codigo, status) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), consultation_id, request.site, "aguardando_manual"),
            )
            _record_event(connection, consultation_id, "consulta_iniciada", {
                "sites": [request.site], "documento_mascarado": masked, "modo": "MANUAL",
            })
            audit_payload = json.dumps(
                [consultation_id, "iniciada_manual", masked, [request.site], started_at, previous],
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO consulta_auditoria (consulta_id, acao, documento_mascarado, sites_consultados, timestamp, hash_anterior, registro_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    consultation_id,
                    "iniciada_manual",
                    masked,
                    json.dumps([request.site]),
                    started_at,
                    previous,
                    hashlib.sha256(audit_payload.encode("utf-8")).hexdigest(),
                ),
            )
            consultation = _serialize_consultation(connection, consultation_id)
    portal = next(site for site in SITE_CATALOG if site["codigo"] == request.site)
    return {
        "consulta_id": consultation_id,
        "status": consultation["status"],
        "consulta": consultation,
        "pasta_destino": str(consultation_directory.resolve()),
        "url": portal["url"],
        "nome_pdf": f"{MANUAL_PDF_FILE_IDS[request.site]}.pdf",
    }


@app.post("/api/v1/consultas/{consultation_id}/sites/simples_nacional/manual")
def continue_simples_nacional_manually(consultation_id: str):
    with closing(_connect()) as connection, connection:
        consultation = connection.execute(
            "SELECT documento_tipo, status FROM consultas WHERE id = ?",
            (consultation_id,),
        ).fetchone()
        site = connection.execute(
            "SELECT status FROM consulta_sites WHERE consulta_id = ? AND site_codigo = 'simples_nacional'",
            (consultation_id,),
        ).fetchone()
        if consultation is None or site is None:
            raise HTTPException(status_code=404, detail="Consulta Simples Nacional não encontrada.")
        if site["status"] != "erro":
            raise HTTPException(status_code=409, detail="A contingência manual só pode ser aberta após falha da automação.")
        connection.execute(
            "UPDATE consulta_sites SET status = 'aguardando_manual', resultado = ? "
            "WHERE consulta_id = ? AND site_codigo = 'simples_nacional'",
            (json.dumps({"detalhe": "Automação interrompida; aguardando emissão manual do PDF oficial."}, ensure_ascii=False), consultation_id),
        )
        connection.execute(
            "UPDATE consultas SET status = 'aguardando_manual' WHERE id = ?",
            (consultation_id,),
        )
        _record_event(connection, consultation_id, "site_status", {
            "site_codigo": "simples_nacional",
            "status": "aguardando_manual",
            "detalhe": "Abra o portal oficial e salve simples_nacional.pdf na pasta desta sessão.",
        })
        row = connection.execute(
            "SELECT documento_hash, iniciado_em FROM consultas WHERE id = ?",
            (consultation_id,),
        ).fetchone()
    directory = find_consultation_directory(row["documento_hash"], row["iniciado_em"], OUTPUT_ROOT)
    if directory is None:
        raise HTTPException(status_code=404, detail="Pasta da consulta não encontrada.")
    portal = next(site for site in SITE_CATALOG if site["codigo"] == "simples_nacional")
    return {
        "consulta_id": consultation_id,
        "status": "aguardando_manual",
        "pasta_destino": str(directory.resolve()),
        "url": portal["url"],
        "nome_pdf": f"{MANUAL_PDF_FILE_IDS['simples_nacional']}.pdf",
    }


@app.get("/api/v1/consultas")
def list_consultations():
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT id FROM consultas ORDER BY iniciado_em DESC LIMIT 25"
        ).fetchall()
        return {"consultas": [_serialize_consultation(connection, row["id"]) for row in rows]}


@app.get("/api/v1/consultas/{consultation_id}")
def get_consultation(consultation_id: str):
    with closing(_connect()) as connection:
        return {"consulta": _serialize_consultation(connection, consultation_id)}


@app.post("/api/v1/consultas/{consultation_id}/captcha/{captcha_id}")
def resolve_captcha(consultation_id: str, captcha_id: str, resolution: CaptchaResolution):
    with CAPTCHA_LOCK:
        gate = PENDING_CAPTCHAS.get(captcha_id)
        if gate is None:
            raise HTTPException(status_code=410, detail="Captcha expirado ou já respondido.")
        with closing(_connect()) as connection:
            captcha = connection.execute(
                "SELECT tipo, status FROM captchas_pendentes WHERE id = ? AND consulta_id = ?",
                (captcha_id, consultation_id),
            ).fetchone()
        if captcha is None or captcha["status"] != "aguardando":
            raise HTTPException(status_code=404, detail="Captcha pendente não encontrado.")
        if resolution.resposta.lower() != "concluido":
            raise HTTPException(status_code=422, detail="Resolva o CAPTCHA na aba oficial do portal e confirme aqui.")
        gate["answer"] = "concluido"
        gate["event"].set()
    return {"status": "resposta_enviada"}


@app.get("/api/v1/consultas/{consultation_id}/sites/{site_code}/pdf")
def download_site_pdf(consultation_id: str, site_code: str):
    with closing(_connect()) as connection:
        consultation = connection.execute(
            "SELECT consulta_sites.status, consulta_sites.resultado, consultas.documento_hash, consultas.iniciado_em "
            "FROM consulta_sites JOIN consultas ON consultas.id = consulta_sites.consulta_id "
            "WHERE consulta_sites.consulta_id = ? AND consulta_sites.site_codigo = ?",
            (consultation_id, site_code),
        ).fetchone()
    if consultation is None or consultation["status"] != "sucesso" or not consultation["resultado"]:
        raise HTTPException(status_code=404, detail="PDF ainda não disponível.")
    flow_code = {"compras_gov": "sicaf", "receita_cnpj": "receita_inss_cnpj", "receita_cpf": "receita_inss_cpf", "fgts_crf": "fgts", "cnj_improbidade": "inelegibilidade_cnj", "cgu_certidoes": "ceis_cgu", "receita_cnpj_comprovante": "cartao_cnpj", "tcu_licitantes": "tcu_inidoneos"}.get(site_code, site_code)
    flow = SITE_FLOWS.get(flow_code)
    consultation_directory = find_consultation_directory(
        consultation["documento_hash"], consultation["iniciado_em"], OUTPUT_ROOT
    )
    if flow is None or consultation_directory is None:
        raise HTTPException(status_code=404, detail="Pasta da consulta não encontrada.")
    file_path = (consultation_directory / f"{flow.get('file_id', flow_code)}.pdf").resolve()
    if file_path.parent != consultation_directory.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo da certidão não encontrado.")
    return FileResponse(file_path, media_type="application/pdf", filename=file_path.name)


@app.post("/api/v1/consultas/{consultation_id}/pdf/unir")
def merge_consultation_pdfs(consultation_id: str, request: MergePdfsRequest):
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT documento_hash, iniciado_em FROM consultas WHERE id = ?",
            (consultation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    directory = find_consultation_directory(row["documento_hash"], row["iniciado_em"], OUTPUT_ROOT)
    if directory is None:
        raise HTTPException(status_code=404, detail="Pasta da consulta não encontrada.")

    resolved_directory = directory.resolve()
    source_paths: list[Path] = []
    for filename in request.arquivos:
        if filename.casefold() == "certidoes_unificadas.pdf":
            raise HTTPException(status_code=422, detail="O PDF unificado anterior não pode ser usado como origem.")
        source = (directory / filename).resolve()
        if source.parent != resolved_directory or not source.is_file():
            raise HTTPException(status_code=404, detail=f"PDF não encontrado na pasta da sessão: {filename}")
        try:
            with source.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise HTTPException(status_code=422, detail=f"Arquivo inválido ou ainda incompleto: {filename}")
                reader = PdfReader(handle, strict=True)
                if reader.is_encrypted:
                    raise HTTPException(status_code=422, detail=f"PDF protegido por senha não pode ser unido: {filename}")
                if len(reader.pages) == 0:
                    raise HTTPException(status_code=422, detail=f"PDF sem páginas: {filename}")
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=422, detail=f"Não foi possível ler o PDF {filename}.") from error
        source_paths.append(source)

    merged_path = directory / "certidoes_unificadas.pdf"
    writer = PdfWriter()
    try:
        for source in source_paths:
            writer.append(str(source))
        temporary_path = directory / ".certidoes_unificadas.tmp.pdf"
        with temporary_path.open("wb") as output:
            writer.write(output)
        writer.close()
        if not temporary_path.read_bytes().startswith(b"%PDF-"):
            temporary_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Falha ao validar o PDF unificado.")
        temporary_path.replace(merged_path)
    except HTTPException:
        raise
    except Exception as error:
        temporary_path = directory / ".certidoes_unificadas.tmp.pdf"
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Não foi possível unir os PDFs selecionados.") from error
    finally:
        writer.close()

    return FileResponse(merged_path, media_type="application/pdf", filename=merged_path.name)


def _open_directory(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], shell=False)
    else:
        subprocess.Popen(["xdg-open", str(path)], shell=False)


@app.post("/api/v1/consultas/{consultation_id}/abrir-pasta")
def open_consultation_directory(consultation_id: str):
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT documento_hash, iniciado_em FROM consultas WHERE id = ?",
            (consultation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    directory = find_consultation_directory(row["documento_hash"], row["iniciado_em"], OUTPUT_ROOT)
    if directory is None:
        raise HTTPException(status_code=404, detail="Pasta da consulta não encontrada.")
    _open_directory(directory)
    return {"status": "pasta_aberta"}


@app.websocket("/api/v1/consultas/{consultation_id}/stream")
async def consultation_stream(websocket: WebSocket, consultation_id: str):
    await websocket.accept()
    last_event_id = 0
    try:
        while True:
            with closing(_connect()) as connection:
                events = connection.execute(
                    "SELECT id, evento, payload, criado_em FROM consulta_eventos WHERE consulta_id = ? AND id > ? ORDER BY id LIMIT 100",
                    (consultation_id, last_event_id),
                ).fetchall()
            for event in events:
                last_event_id = event["id"]
                await websocket.send_json({"id": event["id"], "evento": event["evento"], **json.loads(event["payload"]), "criado_em": event["criado_em"]})
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return


def run() -> None:
    uvicorn.run("certhub.web:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()