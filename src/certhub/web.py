from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
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
from pydantic import BaseModel, Field, field_validator, model_validator

from certhub.core.validators import validate_cnpj, validate_cpf
from certhub.config import load_certidoes_config
from certhub.site_automation import SITE_FLOWS, run_site


SITE_CATALOG = [
    {"codigo": "sicaf", "nome": "Compras.gov.br · Acesse sua Conta", "orgao": "Compras.gov.br", "captcha": "Imagem", "url": "https://comprasnet.gov.br/seguro/loginPortalUASG.asp"},
    {"codigo": "receita_inss_cnpj", "nome": "Certidão de Pessoa Jurídica (CNPJ)", "orgao": "Receita Federal", "captcha": "reCAPTCHA", "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj#"},
    {"codigo": "receita_inss_cpf", "nome": "Certidão de Pessoa Física (CPF)", "orgao": "Receita Federal", "captcha": "reCAPTCHA", "url": "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cpf#"},
    {"codigo": "fgts", "nome": "Certificado de Regularidade do FGTS (CRF)", "orgao": "Caixa Econômica Federal", "captcha": "Verificar no portal", "url": "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"},
    {"codigo": "cndt", "nome": "Certidão Negativa de Débitos Trabalhistas (CNDT)", "orgao": "Tribunal Superior do Trabalho", "captcha": "Manual, se solicitado", "url": "https://www.tst.jus.br/certidao"},
    {"codigo": "inelegibilidade_cnj", "nome": "Cadastro Nacional de Condenações Cíveis por Ato de Improbidade Administrativa e Inelegibilidade", "orgao": "Conselho Nacional de Justiça", "captcha": "Manual, se solicitado", "url": "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php?validar=form"},
    {"codigo": "ceis_cgu", "nome": "Sistema de Certidões da Controladoria-Geral da União", "orgao": "Controladoria-Geral da União", "captcha": "Manual, se solicitado", "url": "https://certidoes.cgu.gov.br/"},
    {"codigo": "cartao_cnpj", "nome": "Comprovante de Inscrição e de Situação Cadastral (CNPJ)", "orgao": "Receita Federal", "captcha": "reCAPTCHA", "url": "https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp"},
    {"codigo": "tcu_inidoneos", "nome": "Certidão de Licitantes Inidôneos (TCU)", "orgao": "Tribunal de Contas da União", "captcha": "Manual, se solicitado", "url": "https://certidoes.apps.tcu.gov.br/emitir-certidao-inidoneos"},
    {"codigo": "simples_nacional", "nome": "Consulta Optantes pelo Simples Nacional", "orgao": "Receita Federal", "captcha": "hCaptcha", "url": "https://www8.receita.fazenda.gov.br/simplesnacional/aplicacoes.aspx?id=21"},
]
for site in SITE_CATALOG:
    flow = SITE_FLOWS.get(site["codigo"])
    if flow is not None:
        site["url"] = flow["url"]
_CONFIGURED_PORTALS = load_certidoes_config().get("portais", [])
for portal in _CONFIGURED_PORTALS if isinstance(_CONFIGURED_PORTALS, list) else []:
    if not isinstance(portal, dict):
        continue
    site_code = {"compras_gov": "sicaf"}.get(portal.get("id"), portal.get("id"))
    site = next((item for item in SITE_CATALOG if item["codigo"] == site_code), None)
    if site is None:
        continue
    site["url"] = portal.get("url_servico") or portal.get("url_inicial") or site["url"]
    site["captcha"] = "Acesso manual" if portal.get("tipo") == "manual" else site["captcha"]
SITE_CODES = {site["codigo"] for site in SITE_CATALOG}
IMPLEMENTED_SITE_CODES = {"inelegibilidade_cnj", "receita_inss_cnpj", "fgts"}
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
PROJECT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
SITE_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="certhub-site")
CAPTCHA_LOCK = threading.Lock()
PENDING_CAPTCHAS: dict[str, dict] = {}
OUTPUT_ROOT = Path("output/consultas")
INITIALIZED_DATABASES: set[str] = set()
DATABASE_INIT_LOCK = threading.Lock()


def _database_path() -> Path:
    return Path(os.getenv("CERTHUB_DB_PATH", "data/consultas_demo.sqlite3"))


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
                "integration_configured": site["codigo"] in IMPLEMENTED_SITE_CODES,
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
    with closing(_connect()) as connection, connection:
        connection.execute(
            "UPDATE consulta_sites SET status = ?, resultado = ? WHERE consulta_id = ? AND site_codigo = ?",
            (status, json.dumps(result, ensure_ascii=False) if result is not None else None, consultation_id, site_code),
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
        _record_event(connection, consultation_id, event_name, {"site_codigo": site_code, "status": status, "resultado": result})


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


def _run_site_task(consultation_id: str, site_code: str, document: str) -> None:
    try:
        result = run_site(
            consultation_id,
            site_code,
            document,
            lambda code, status, detail: _set_site_status(consultation_id, code, status, {"detalhe": detail} if detail else None),
            lambda code, kind, image, selector: _wait_for_human_captcha(consultation_id, code, kind, image, selector),
            OUTPUT_ROOT,
        )
    except Exception as error:
        _set_site_status(consultation_id, site_code, "erro", {"erro": str(error)[:500]})
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
    return {
        "id": row["id"],
        "documento_tipo": row["documento_tipo"],
        "documento_mascarado": row["documento_mascarado"],
        "status": row["status"],
        "iniciado_em": row["iniciado_em"],
        "sites": [
            {
                "codigo": item["site_codigo"],
                "status": item["status"],
                "resultado": json.loads(item["resultado"]) if item["resultado"] else None,
            }
            for item in site_rows
        ],
        "resultados_consolidados": [
            {"site_codigo": item["site_codigo"], **json.loads(item["resultado"])}
            for item in site_rows
            if item["status"] == "sucesso" and item["resultado"]
        ],
    }


@app.post("/api/v1/consultas", status_code=202)
def create_consultation(request: ConsultationRequest):
    digits = request.normalized_document()
    masked = _mask_document(request.tipo, digits)
    consultation_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    with closing(_connect()) as connection, connection:
        last_audit = connection.execute(
            "SELECT registro_hash FROM consulta_auditoria ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous = last_audit["registro_hash"] if last_audit else None
        connection.execute(
            "INSERT INTO consultas (id, documento_tipo, documento_hash, documento_mascarado, status, iniciado_em) VALUES (?, ?, ?, ?, ?, ?)",
            (
                consultation_id,
                request.tipo,
                hashlib.sha256(digits.encode("ascii")).hexdigest(),
                masked,
                "em_andamento",
                started_at,
            ),
        )
        connection.executemany(
            "INSERT INTO consulta_sites (id, consulta_id, site_codigo, status) VALUES (?, ?, ?, ?)",
            [(str(uuid.uuid4()), consultation_id, code, "pendente") for code in request.sites],
        )
        _record_event(connection, consultation_id, "consulta_iniciada", {"sites": request.sites, "documento_mascarado": masked})
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
    for site_code in request.sites:
        SITE_EXECUTOR.submit(_run_site_task, consultation_id, site_code, digits)
    return {"consulta_id": consultation_id, "status": consultation["status"], "consulta": consultation}


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
        if captcha["tipo"] != "imagem" and resolution.resposta.lower() != "concluido":
            raise HTTPException(status_code=422, detail="Conclua o desafio na janela do portal e confirme aqui.")
        gate["answer"] = resolution.resposta if captcha["tipo"] == "imagem" else "concluido"
        gate["event"].set()
    return {"status": "resposta_enviada"}


@app.get("/api/v1/consultas/{consultation_id}/sites/{site_code}/pdf")
def download_site_pdf(consultation_id: str, site_code: str):
    with closing(_connect()) as connection:
        consultation = connection.execute(
            "SELECT status, resultado FROM consulta_sites WHERE consulta_id = ? AND site_codigo = ?",
            (consultation_id, site_code),
        ).fetchone()
    if consultation is None or consultation["status"] != "sucesso" or not consultation["resultado"]:
        raise HTTPException(status_code=404, detail="PDF ainda não disponível.")
    result = json.loads(consultation["resultado"])
    file_path = Path(result.get("pdf_path", "")).resolve()
    output_root = OUTPUT_ROOT.resolve()
    if output_root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo da certidão não encontrado.")
    return FileResponse(file_path, media_type="application/pdf", filename=file_path.name)


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