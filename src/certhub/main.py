from __future__ import annotations

import re
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from certhub import __version__
from certhub.config import create_consultation_directory, get_setting
from certhub.core.models import EmissionRequest
from certhub.site_automation import SITE_FLOWS, SiteAutomationError, run_site
from certhub.portals import (
    CEISPortal,
    CNDTPortal,
    CartaoCNPJPortal,
    CNJPortal,
    FGTSPortal,
    ReceitaCNPJPortal,
    ReceitaCPFPortal,
    SICAFPortal,
    SimplesNacionalPortal,
    TCUPortal,
)

app = typer.Typer(
    help="CertHub - Todas as certidões em um só lugar",
    invoke_without_command=True,
    no_args_is_help=True,
)
console = Console()

PORTAL_REGISTRY = {
    "fgts": FGTSPortal,
    "cndt": CNDTPortal,
    "receita_cnpj": ReceitaCNPJPortal,
    "receita_cpf": ReceitaCPFPortal,
    "simples_nacional": SimplesNacionalPortal,
    "ceis": CEISPortal,
    "cnj": CNJPortal,
    "tcu": TCUPortal,
    "cartao_cnpj": CartaoCNPJPortal,
    "sicaf": SICAFPortal,
}
PORTAL_FLOW_CODES = {
    "fgts": "fgts",
    "cndt": "cndt",
    "cnj": "inelegibilidade_cnj",
    "receita_cnpj": "receita_inss_cnpj",
    "receita_cpf": "receita_inss_cpf",
    "ceis": "ceis_cgu",
    "tcu": "tcu_inidoneos",
    "cartao_cnpj": "cartao_cnpj",
    "sicaf": "sicaf",
    "simples_nacional": "simples_nacional",
}
IMPLEMENTED_PORTAL_FLOWS = {
    flow_code for flow_code, flow in SITE_FLOWS.items() if flow.get("implemented")
}


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version"),
):
    if version:
        typer.echo(f"CertHub v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command("emitir")
def emitir_documento(
    portal: str = typer.Option(..., "--portal", help="Portal a ser consultado."),
    documento: str = typer.Option(..., "--documento", help="CNPJ ou CPF."),
    data_nascimento: str | None = typer.Option(None, "--data-nascimento", help="Data de nascimento (AAAA-MM-DD), obrigatória para Receita CPF."),
    debug: bool = typer.Option(False, "--debug", help="Ativa modo visível."),
    hitl: bool = typer.Option(False, "--hitl", help="Ativa fallback manual."),
):
    portal_cls = PORTAL_REGISTRY.get(portal.lower())
    if portal_cls is None:
        raise typer.BadParameter(f"Portal '{portal}' não suportado. Portais válidos: {', '.join(PORTAL_REGISTRY)}")
    flow_code = PORTAL_FLOW_CODES.get(portal.lower(), portal.lower())
    if flow_code not in IMPLEMENTED_PORTAL_FLOWS:
        raise typer.BadParameter(f"Macro do portal '{portal}' ainda não implementado.")

    request = EmissionRequest(portal=portal.lower(), document=documento, headless=not (debug or hitl))
    if flow_code == "receita_inss_cpf" and not data_nascimento:
        raise typer.BadParameter("--data-nascimento é obrigatório para Receita CPF (formato AAAA-MM-DD).")
    portal_instance = portal_cls(request)
    consultation_id = str(uuid.uuid4())
    try:
        portal_instance.validate()
        output_directory, _ = create_consultation_directory(re.sub(r"\D", "", documento))

        def resolve_captcha(site_code: str, captcha_type: str, image_base64: str | None, selector: str | None):
            if not hitl:
                console.print("[yellow]Captcha detectado. Execute novamente com --hitl para resolução humana.[/yellow]")
                return None
            if captcha_type == "token":
                console.print("Autentique no SICAF e deixe a página oficial da certidão aberta.")
            else:
                console.print(f"Resolva o CAPTCHA na aba oficial do portal {site_code}.")
            typer.prompt("Pressione Enter quando a página estiver pronta", default="concluido", show_default=False)
            return "concluido"

        result = run_site(
            consultation_id,
            flow_code,
            re.sub(r"\D", "", documento),
            lambda code, status, detail: None,
            resolve_captcha,
            output_directory,
            headless=not (debug or hitl),
            additional_data={"data_nascimento": data_nascimento, "tipo": "CPF" if flow_code in {"receita_inss_cpf"} or len(re.sub(r"\D", "", documento)) == 11 else "CNPJ"},
        )
    except (ValueError, SiteAutomationError) as error:
        console.print(f"[red]Falha[/red]: {error}")
        raise typer.Exit(code=1) from error
    finally:
        portal_instance.close_browser()

    console.print(f"[green]PDF baixado e validado[/green]: {result['arquivo']}")
    console.print(f"Pasta: {output_directory}")
    console.print(f"PDF: {result['pdf_path']}")
    console.print(f"Hash SHA-256: {result['pdf_sha256']}")


@app.command("listar-portais")
def listar_portais():
    table = Table(title="Portais disponíveis")
    table.add_column("Portal")
    table.add_column("Modo")
    table.add_column("Estado")
    for name in PORTAL_REGISTRY:
        flow_code = PORTAL_FLOW_CODES.get(name, name)
        flow = SITE_FLOWS.get(flow_code, {})
        mode = flow.get("execution_mode", "INTERNO")
        state = "Disponível" if flow.get("implemented") else "Em implementação — não executável"
        table.add_row(name, mode, state)
    console.print(table)


@app.command("validar-config")
def validar_config():
    config = get_setting("certhub", default={})
    if config:
        console.print("[green]Configuração válida.[/green]")
        console.print(f"Nome: {config.get('nome', 'CertHub')}")
    else:
        console.print("[yellow]Arquivo de configuração não encontrado; usando valores padrão.[/yellow]")


if __name__ == "__main__":
    app()
