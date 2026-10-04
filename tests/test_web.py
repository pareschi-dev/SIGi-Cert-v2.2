import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

import certhub.web as web_module
from certhub.config import load_certidoes_config
from certhub.web import (
    CAPTCHA_LOCK,
    MAX_CONCURRENT_SITE_TASKS,
    PENDING_CAPTCHAS,
    SITE_EXECUTION_MODES,
    SITE_EXECUTOR,
    _connect,
    app,
)


@pytest.fixture(autouse=True)
def prevent_external_portal_access(monkeypatch):
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda *args, **kwargs: None)


def test_site_executor_limits_concurrency_to_three_portals():
    assert MAX_CONCURRENT_SITE_TASKS == 3


def test_automated_portals_are_submitted_without_manual_portals(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    submitted_sites = []
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: submitted_sites.append(args[1]))
    client = TestClient(app)

    response = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["receita_inss_cnpj", "tcu_inidoneos"],
    })

    assert response.status_code == 202
    assert submitted_sites == [
        "receita_inss_cnpj", "tcu_inidoneos",
    ]


def test_sequential_automated_portal_consultations_share_one_folder(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    submitted_sites = []
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: submitted_sites.append(args[1]))
    client = TestClient(app)

    first = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj"],
    })
    assert first.status_code == 202
    initial = first.json()

    second = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["tcu_inidoneos"],
        "consulta_id": initial["consulta_id"],
    })

    assert second.status_code == 202
    appended = second.json()
    assert appended["consulta_id"] == initial["consulta_id"]
    assert appended["pasta_destino"] == initial["pasta_destino"]
    assert len(list(output_root.iterdir())) == 1
    assert {site["codigo"] for site in appended["consulta"]["sites"]} == {
        "inelegibilidade_cnj", "tcu_inidoneos",
    }
    assert submitted_sites == ["inelegibilidade_cnj", "tcu_inidoneos"]


def test_manual_portal_session_opens_link_without_running_automation(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    submitted = []
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda *args, **kwargs: submitted.append(args))
    client = TestClient(app)

    response = client.post("/api/v1/consultas/manual", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "site": "cndt",
    })

    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://cndt-certidao.tst.jus.br/"
    assert body["nome_pdf"] == "cndt.pdf"
    assert body["status"] == "aguardando_manual"
    assert body["consulta"]["sites"][0]["status"] == "aguardando_manual"
    assert Path(body["pasta_destino"]).is_dir()
    assert submitted == []

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    with (Path(body["pasta_destino"]) / "cndt.pdf").open("wb") as pdf_file:
        writer.write(pdf_file)

    completed = client.get(f"/api/v1/consultas/{body['consulta_id']}").json()["consulta"]
    assert completed["status"] == "concluida"
    assert completed["sites"][0]["status"] == "sucesso"
    assert completed["sites"][0]["resultado"]["pdf_sha256"]


def test_manual_portal_reuses_active_consultation_folder(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    client = TestClient(app)

    automated = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj"],
    }).json()
    consultation_id = automated["consulta_id"]
    original_folder = Path(automated["pasta_destino"])

    manual = client.post("/api/v1/consultas/manual", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "site": "cndt",
        "consulta_id": consultation_id,
    })

    assert manual.status_code == 201
    body = manual.json()
    assert body["consulta_id"] == consultation_id
    assert Path(body["pasta_destino"]) == original_folder
    assert len(list(output_root.iterdir())) == 1
    assert {site["codigo"] for site in body["consulta"]["sites"]} == {
        "inelegibilidade_cnj", "cndt",
    }

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    with (original_folder / "cndt.pdf").open("wb") as pdf_file:
        writer.write(pdf_file)
    refreshed = client.get(f"/api/v1/consultas/{consultation_id}").json()["consulta"]

    assert refreshed["pasta_destino"] == str(original_folder.resolve())
    assert next(site for site in refreshed["sites"] if site["codigo"] == "cndt")["status"] == "sucesso"
    assert {item["nome"] for item in refreshed["arquivos_pdf"]} == {"cndt.pdf"}


def test_automated_consultation_rejects_manual_only_portals(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    response = TestClient(app).post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["cndt"],
    })

    assert response.status_code == 422
    assert "Macros ainda não implementados" in str(response.json()["detail"])


def test_each_captcha_portal_starts_its_own_manual_session(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    submitted = []
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda *args, **kwargs: submitted.append(args))
    client = TestClient(app)
    sessions = []
    for site_code in ("cndt", "ceis_cgu", "cartao_cnpj", "sicaf"):
        response = client.post("/api/v1/consultas/manual", json={
            "documento": "12.345.678/0001-95",
            "tipo": "CNPJ",
            "site": site_code,
        })
        assert response.status_code == 201
        sessions.append(response.json())

    assert {session["consulta"]["sites"][0]["codigo"] for session in sessions} == {
        "cndt", "ceis_cgu", "cartao_cnpj", "sicaf",
    }
    assert {session["nome_pdf"] for session in sessions} == {
        "cndt.pdf", "cgu_certidoes.pdf", "receita_cnpj_comprovante.pdf", "compras_gov.pdf",
    }
    assert len({session["pasta_destino"] for session in sessions}) == 4
    assert submitted == []


def test_create_consultation_stores_only_document_hash(monkeypatch, tmp_path):
    database = tmp_path / "consultas.sqlite3"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(database))
    client = TestClient(app)

    response = client.post(
        "/api/v1/consultas",
        json={
            "documento": "12.345.678/0001-95",
            "tipo": "CNPJ",
            "sites": ["inelegibilidade_cnj"],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "em_andamento"
    assert "finalidade" not in body["consulta"]
    assert body["consulta"]["documento_mascarado"] == "**.***.***/****-95"
    assert [site["codigo"] for site in body["consulta"]["sites"]] == ["inelegibilidade_cnj"]
    assert all(site["status"] == "pendente" for site in body["consulta"]["sites"])

    with sqlite3.connect(database) as connection:
        stored_document = connection.execute("SELECT documento_hash FROM consultas").fetchone()[0]
        assert stored_document != "12345678000195"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(consultas)")}
        assert "finalidade" not in columns
        assert connection.execute("SELECT COUNT(*) FROM consulta_auditoria").fetchone()[0] == 1


def test_consultation_mirrors_pdfs_saved_manually_into_session_folder(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    client = TestClient(app)

    created = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj"],
    })
    session_folder = Path(created.json()["pasta_destino"])
    (session_folder / "cndt.pdf").write_bytes(b"%PDF-1.7\nmanual certificate\n")
    (session_folder / "incompleto.pdf").write_bytes(b"not a PDF")

    response = client.get(f"/api/v1/consultas/{created.json()['consulta_id']}")

    assert response.status_code == 200
    files = {item["nome"]: item for item in response.json()["consulta"]["arquivos_pdf"]}
    assert files["cndt.pdf"]["valido"] is True
    assert files["cndt.pdf"]["sha256"]
    assert files["incompleto.pdf"]["valido"] is False


def test_merge_consultation_pdfs_uses_requested_order_and_stays_in_session_folder(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    client = TestClient(app)
    created = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj"],
    })
    session_folder = Path(created.json()["pasta_destino"])
    for filename, width in (("first.pdf", 100), ("second.pdf", 300)):
        writer = PdfWriter()
        writer.add_blank_page(width=width, height=200)
        with (session_folder / filename).open("wb") as pdf_file:
            writer.write(pdf_file)

    response = client.post(
        f"/api/v1/consultas/{created.json()['consulta_id']}/pdf/unir",
        json={"arquivos": ["second.pdf", "first.pdf"]},
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"].find("certidoes_unificadas.pdf") >= 0
    assert response.content.startswith(b"%PDF-")
    merged_path = session_folder / "certidoes_unificadas.pdf"
    assert merged_path.read_bytes() == response.content
    merged = PdfReader(merged_path)
    assert [float(page.mediabox.width) for page in merged.pages] == [300.0, 100.0]


def test_migrates_legacy_database_without_finalidade(monkeypatch, tmp_path):
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE consultas (id TEXT PRIMARY KEY, documento_tipo TEXT NOT NULL, documento_hash TEXT NOT NULL, documento_mascarado TEXT NOT NULL, finalidade TEXT NOT NULL, status TEXT NOT NULL, iniciado_em TEXT NOT NULL)"
        )
    monkeypatch.setenv("CERTHUB_DB_PATH", str(database))

    connection = _connect()
    columns = {row[1] for row in connection.execute("PRAGMA table_info(consultas)")}
    connection.close()

    assert "finalidade" not in columns


def test_rejects_invalid_document_and_unknown_site(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)
    base_payload = {
        "documento": "12.345.678/0001-90",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj"],
    }

    invalid_document = client.post("/api/v1/consultas", json=base_payload)
    assert invalid_document.status_code == 422

    base_payload["documento"] = "12.345.678/0001-95"
    base_payload["sites"] = ["site-inexistente"]
    unknown_site = client.post("/api/v1/consultas", json=base_payload)
    assert unknown_site.status_code == 422


def test_sicaf_uses_separate_manual_token_session(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)

    response = client.post("/api/v1/consultas/manual", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "site": "sicaf",
    })

    assert response.status_code == 201
    assert response.json()["url"] == "https://www3.comprasnet.gov.br/sicaf-web/index.jsf"
    assert response.json()["nome_pdf"] == "compras_gov.pdf"
    assert response.json()["status"] == "aguardando_manual"


def test_simples_nacional_manual_fallback_is_available_for_hcaptcha(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    client = TestClient(app)

    catalog_site = next(
        site for site in client.get("/api/v1/sites/catalogo").json()["sites"]
        if site["codigo"] == "simples_nacional"
    )
    response = client.post("/api/v1/consultas/manual", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "site": "simples_nacional",
    })

    assert catalog_site["integration_configured"] is True
    assert catalog_site["manual_only"] is False
    assert response.status_code == 201
    assert response.json()["url"] == web_module.SITE_FLOWS["simples_nacional"]["url"]
    assert response.json()["nome_pdf"] == "simples_nacional.pdf"


def test_simples_nacional_error_continues_manually_in_same_session(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(
        web_module,
        "run_site",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated hCaptcha")),
    )
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: function(*args))
    client = TestClient(app)
    created = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["simples_nacional"],
    })
    consultation_id = created.json()["consulta_id"]
    original_folder = Path(created.json()["pasta_destino"])

    fallback = client.post(f"/api/v1/consultas/{consultation_id}/sites/simples_nacional/manual")
    assert fallback.status_code == 200
    assert Path(fallback.json()["pasta_destino"]) == original_folder
    assert fallback.json()["nome_pdf"] == "simples_nacional.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    with (original_folder / "simples_nacional.pdf").open("wb") as pdf_file:
        writer.write(pdf_file)

    completed = client.get(f"/api/v1/consultas/{consultation_id}").json()["consulta"]
    assert completed["status"] == "concluida"
    assert completed["sites"][0]["status"] == "sucesso"
    assert completed["sites"][0]["resultado"]["pdf_sha256"]


def test_receita_cpf_requires_birth_date_before_starting(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)
    base = {"documento": "529.982.247-25", "tipo": "CPF", "sites": ["receita_inss_cpf"]}

    missing_date = client.post("/api/v1/consultas", json=base)
    with_date = client.post("/api/v1/consultas", json={**base, "data_nascimento": "2000-01-01"})

    assert missing_date.status_code == 422
    assert with_date.status_code == 202


def test_receita_cpf_birth_date_is_passed_transiently_not_persisted(monkeypatch, tmp_path):
    database = tmp_path / "consultas.sqlite3"
    downloads = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(database))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", downloads)
    captured = {}

    def fake_run_site(consultation_id, site_code, document, on_status, on_captcha, target_root, additional_data=None, **kwargs):
        captured.update(site=site_code, document=document, additional_data=additional_data)
        target = target_root / "receita_cpf.pdf"
        target.write_bytes(b"%PDF-1.4\n%cpf fixture\n")
        return {"site_codigo": site_code, "pdf_path": str(target), "pdf_sha256": "c" * 64, "arquivo": target.name}

    monkeypatch.setattr(web_module, "run_site", fake_run_site)
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: function(*args))
    client = TestClient(app)
    response = client.post("/api/v1/consultas", json={
        "documento": "529.982.247-25",
        "tipo": "CPF",
        "data_nascimento": "2000-01-02",
        "sites": ["receita_inss_cpf"],
    })

    assert response.status_code == 202
    assert captured == {
        "site": "receita_inss_cpf",
        "document": "52998224725",
        "additional_data": {"data_nascimento": "2000-01-02", "tipo": "CPF"},
    }
    with sqlite3.connect(database) as connection:
        stored_text = " ".join(str(value) for row in connection.execute("SELECT * FROM consultas") for value in row)
        stored_text += " ".join(row[0] for row in connection.execute("SELECT payload FROM consulta_eventos"))
    assert "2000-01-02" not in stored_text
    assert "52998224725" not in stored_text


def test_accepts_formatted_cnpj_with_surrounding_spaces(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)

    response = client.post(
        "/api/v1/consultas",
        json={
            "documento": " 12.345.678/0001-95 ",
            "tipo": "CNPJ",
            "sites": ["inelegibilidade_cnj"],
        },
    )

    assert response.status_code == 202
    assert response.json()["consulta"]["documento_mascarado"] == "**.***.***/****-95"


def test_catalog_and_api_status(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)

    catalog = client.get("/api/v1/sites/catalogo")
    history = client.get("/api/v1/consultas")

    assert catalog.status_code == 200
    assert len(catalog.json()["sites"]) == 10
    assert {site["codigo"]: site["nome"] for site in catalog.json()["sites"]} == {
        "sicaf": "SICAF — Compras.gov.br",
        "receita_inss_cnpj": "Certidão de Pessoa Jurídica (CNPJ)",
        "receita_inss_cpf": "Certidão de Pessoa Física (CPF)",
        "fgts": "Certificado de Regularidade do FGTS (CRF)",
        "cndt": "Certidão Negativa de Débitos Trabalhistas (CNDT)",
        "inelegibilidade_cnj": "Cadastro Nacional de Condenações Cíveis por Ato de Improbidade Administrativa e Inelegibilidade",
        "ceis_cgu": "Sistema de Certidões da Controladoria-Geral da União",
        "cartao_cnpj": "Comprovante de Inscrição e de Situação Cadastral (CNPJ)",
        "tcu_inidoneos": "Certidão de Licitantes Inidôneos (TCU)",
        "simples_nacional": "Consulta Optantes pelo Simples Nacional",
    }
    configured = {site["codigo"] for site in catalog.json()["sites"] if site["integration_configured"]}
    manual_captcha_codes = {"cndt", "ceis_cgu", "cartao_cnpj"}
    manual_codes = manual_captcha_codes | {"sicaf"}
    assert configured == {site["codigo"] for site in catalog.json()["sites"]} - manual_codes
    catalog_by_code = {site["codigo"]: site for site in catalog.json()["sites"]}
    expected_modes = {**SITE_EXECUTION_MODES, **{code: "MANUAL" for code in manual_captcha_codes}}
    assert {code: site["execution_mode"] for code, site in catalog_by_code.items()} == expected_modes
    assert {code for code, site in catalog_by_code.items() if site["manual_only"]} == manual_codes
    assert all(not catalog_by_code[code]["integration_configured"] for code in manual_codes)
    assert catalog_by_code["sicaf"]["manual_mode"] == "token"
    assert all(catalog_by_code[code]["manual_mode"] == "captcha" for code in manual_captcha_codes)
    assert all(portal["tipo"] == "automacao" for portal in load_certidoes_config()["portais"])
    cnj = next(site for site in catalog.json()["sites"] if site["codigo"] == "inelegibilidade_cnj")
    assert cnj["url"].endswith("consultar_requerido.php?validar=form")
    assert history.json() == {"consultas": []}


def test_websocket_streams_consultation_events(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)
    response = client.post(
        "/api/v1/consultas",
        json={
            "documento": "12.345.678/0001-95",
            "tipo": "CNPJ",
            "sites": ["inelegibilidade_cnj"],
        },
    )
    consultation_id = response.json()["consulta_id"]

    with client.websocket_connect(f"/api/v1/consultas/{consultation_id}/stream") as websocket:
        event = websocket.receive_json()

    assert event["evento"] == "consulta_iniciada"
    assert event["sites"] == ["inelegibilidade_cnj"]


def test_captcha_confirmation_signals_waiting_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)
    response = client.post(
        "/api/v1/consultas",
        json={
            "documento": "12.345.678/0001-95",
            "tipo": "CNPJ",
            "sites": ["inelegibilidade_cnj"],
        },
    )
    consultation_id = response.json()["consulta_id"]
    captcha_id = "captcha-test-id"
    gate = {"event": threading.Event(), "answer": None}
    with CAPTCHA_LOCK:
        PENDING_CAPTCHAS[captcha_id] = gate
    with _connect() as connection:
        connection.execute(
            "INSERT INTO captchas_pendentes (id, consulta_id, site_codigo, tipo, status, expira_em, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (captcha_id, consultation_id, "inelegibilidade_cnj", "recaptcha", "aguardando", "2099-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )

    result = client.post(
        f"/api/v1/consultas/{consultation_id}/captcha/{captcha_id}",
        json={"resposta": "concluido"},
    )

    assert result.status_code == 200
    assert gate["event"].is_set()
    assert gate["answer"] == "concluido"
    with CAPTCHA_LOCK:
        PENDING_CAPTCHAS.pop(captcha_id, None)


def test_consultation_worker_persists_real_pdf_result(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    output_root = tmp_path / "output"
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)

    def fake_run_site(consultation_id, site_code, document, on_status, on_captcha, target_root, additional_data=None, **kwargs):
        on_status(site_code, "rodando", None)
        pdf_path = target_root / "cnj_improbidade.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4\n%test certificate\n")
        return {"site_codigo": site_code, "pdf_path": str(pdf_path.resolve()), "pdf_sha256": "a" * 64}

    monkeypatch.setattr(web_module, "run_site", fake_run_site)
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: function(*args))
    client = TestClient(app)

    created = client.post(
        "/api/v1/consultas",
        json={
            "documento": "12.345.678/0001-95",
            "tipo": "CNPJ",
            "sites": ["inelegibilidade_cnj"],
        },
    )
    consultation_id = created.json()["consulta_id"]
    result = client.get(f"/api/v1/consultas/{consultation_id}").json()["consulta"]
    downloaded_pdf = client.get(f"/api/v1/consultas/{consultation_id}/sites/inelegibilidade_cnj/pdf")

    assert created.status_code == 202
    assert result["status"] == "concluida", result["sites"]
    assert result["sites"][0]["status"] == "sucesso"
    assert result["resultados_consolidados"][0]["pdf_sha256"] == "a" * 64
    assert result["pasta_disponivel"] is True
    assert Path(created.json()["pasta_destino"]).name.startswith("12345678000195_")
    assert Path(result["pasta_destino"]).name.startswith("12345678000195_")
    assert Path(result["resultados_consolidados"][0]["pdf_path"]).parent == Path(result["pasta_destino"])
    with sqlite3.connect(tmp_path / "consultas.sqlite3") as connection:
        stored_result = connection.execute("SELECT resultado FROM consulta_sites").fetchone()[0]
        stored_events = " ".join(row[0] for row in connection.execute("SELECT payload FROM consulta_eventos"))
    assert "pdf_path" not in stored_result
    assert "12345678000195" not in stored_events
    assert downloaded_pdf.status_code == 200
    assert "attachment" in downloaded_pdf.headers["content-disposition"].lower()
    assert downloaded_pdf.content.startswith(b"%PDF-")


def test_open_folder_endpoint_opens_only_the_consultation_folder(monkeypatch, tmp_path):
    database = tmp_path / "consultas.sqlite3"
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(database))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    opened = []
    monkeypatch.setattr(web_module, "_open_directory", opened.append)
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda *args, **kwargs: None)
    client = TestClient(app)

    response = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj"],
    })
    consultation_id = response.json()["consulta_id"]
    opened_response = client.post(f"/api/v1/consultas/{consultation_id}/abrir-pasta")

    assert opened_response.status_code == 200
    assert opened == [Path(response.json()["pasta_destino"])]


def test_all_portals_in_one_consultation_share_the_same_flat_download_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", tmp_path / "downloads")

    def fake_run_site(consultation_id, site_code, document, on_status, on_captcha, target_root, additional_data=None, **kwargs):
        filenames = {
            "inelegibilidade_cnj": "cnj_improbidade.pdf",
            "receita_inss_cnpj": "receita_cnpj.pdf",
        }
        target = target_root / filenames[site_code]
        target.write_bytes(b"%PDF-1.4\n%official-flow fixture\n")
        return {
            "site_codigo": site_code,
            "pdf_path": str(target),
            "pdf_sha256": "b" * 64,
            "arquivo": target.name,
        }

    monkeypatch.setattr(web_module, "run_site", fake_run_site)
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: function(*args))
    client = TestClient(app)

    created = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["inelegibilidade_cnj", "receita_inss_cnpj"],
    })
    consultation = client.get(f"/api/v1/consultas/{created.json()['consulta_id']}").json()["consulta"]
    destination = Path(consultation["pasta_destino"])

    assert created.status_code == 202
    assert consultation["status"] == "concluida"
    assert {file.name for file in destination.iterdir()} == {"cnj_improbidade.pdf", "receita_cnpj.pdf"}
    assert all(Path(result["pdf_path"]).parent == destination for result in consultation["resultados_consolidados"])