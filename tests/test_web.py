import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


def test_cnpj_captcha_portals_are_submitted_first(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    submitted_sites = []
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: submitted_sites.append(args[1]))
    client = TestClient(app)

    response = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["receita_inss_cnpj", "tcu_inidoneos", "cartao_cnpj", "cndt", "ceis_cgu"],
    })

    assert response.status_code == 202
    assert submitted_sites == [
        "cndt", "ceis_cgu", "cartao_cnpj", "receita_inss_cnpj", "tcu_inidoneos",
    ]


def test_three_cnpj_captcha_pdfs_share_the_consultation_folder(monkeypatch, tmp_path):
    output_root = tmp_path / "downloads"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    monkeypatch.setattr(web_module, "OUTPUT_ROOT", output_root)
    captured_roots = {}

    def fake_run_site(consultation_id, site_code, document, on_status, on_captcha, target_root, additional_data=None, **kwargs):
        captured_roots[site_code] = Path(target_root)
        pdf_path = Path(target_root) / f"{web_module.SITE_FLOWS[site_code]['file_id']}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fixture\n")
        return {"site_codigo": site_code, "pdf_path": str(pdf_path.resolve()), "pdf_sha256": "d" * 64}

    monkeypatch.setattr(web_module, "run_site", fake_run_site)
    monkeypatch.setattr(SITE_EXECUTOR, "submit", lambda function, *args: function(*args))
    client = TestClient(app)

    response = client.post("/api/v1/consultas", json={
        "documento": "12.345.678/0001-95",
        "tipo": "CNPJ",
        "sites": ["cndt", "ceis_cgu", "cartao_cnpj"],
    })

    assert response.status_code == 202
    assert set(captured_roots) == {"cndt", "ceis_cgu", "cartao_cnpj"}
    assert len(set(captured_roots.values())) == 1
    target_root = Path(response.json()["pasta_destino"])
    assert set(path.name for path in target_root.glob("*.pdf")) == {
        "cndt.pdf", "cgu_certidoes.pdf", "receita_cnpj_comprovante.pdf",
    }


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


def test_sicaf_request_is_accepted_for_token_assisted_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("CERTHUB_DB_PATH", str(tmp_path / "consultas.sqlite3"))
    client = TestClient(app)

    response = client.post(
        "/api/v1/consultas",
        json={
            "documento": "12.345.678/0001-95",
            "tipo": "CNPJ",
            "sites": ["sicaf"],
        },
    )

    assert response.status_code == 202
    assert response.json()["consulta"]["sites"][0]["status"] == "pendente"


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
    assert configured == {site["codigo"] for site in catalog.json()["sites"]}
    catalog_by_code = {site["codigo"]: site for site in catalog.json()["sites"]}
    assert {code: site["execution_mode"] for code, site in catalog_by_code.items()} == SITE_EXECUTION_MODES
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