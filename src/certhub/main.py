from __future__ import annotations

import base64
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from certhub import __version__
from certhub.config import get_setting
from certhub.core.models import EmissionRequest
from certhub.site_automation import SiteAutomationError, run_site
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
    "cnj": "inelegibilidade_cnj",
    "receita_cnpj": "receita_inss_cnpj",
    "receita_cpf": "receita_inss_cpf",
    "ceis": "ceis_cgu",
}
IMPLEMENTED_PORTAL_FLOWS = {"inelegibilidade_cnj", "receita_inss_cnpj", "fgts"}


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
    portal_instance = portal_cls(request)
    try:
        portal_instance.validate()

        def resolve_captcha(site_code: str, captcha_type: str, image_base64: str | None, selector: str | None):
            if not hitl:
                console.print("[yellow]Captcha detectado. Execute novamente com --hitl para resolução humana.[/yellow]")
                return None
            if captcha_type == "imagem" and image_base64:
                image_path = Path("output/consultas/captchas") / f"{uuid.uuid4()}.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(base64.b64decode(image_base64))
                console.print(f"Captcha do portal {site_code}; imagem: {image_path.resolve()}")
                try:
                    return typer.prompt("Digite o captcha")
                finally:
                    image_path.unlink(missing_ok=True)
            console.print(f"Resolva o desafio manualmente na janela do portal {site_code}.")
            typer.prompt("Pressione Enter após concluir o desafio", default="concluido", show_default=False)
            return "concluido"

        result = run_site(
            str(uuid.uuid4()),
            flow_code,
            re.sub(r"\D", "", documento),
            lambda code, status, detail: None,
            resolve_captcha,
            headless=not (debug or hitl),
        )
    except (ValueError, SiteAutomationError) as error:
        console.print(f"[red]Falha[/red]: {error}")
        raise typer.Exit(code=1) from error
    finally:
        portal_instance.close_browser()

    console.print(f"[green]PDF baixado e validado[/green]: {result['arquivo']}")
    console.print(f"PDF: {result['pdf_path']}")
    console.print(f"Hash SHA-256: {result['pdf_sha256']}")


@app.command("listar-portais")
def listar_portais():
    table = Table(title="Portais disponíveis")
    table.add_column("Portal")
    table.add_column("Descrição")
    table.add_column("Captcha")
    for name in PORTAL_REGISTRY:
        table.add_row(name, name, "variável")
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
