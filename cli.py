"""CLI entry point for ATF."""

import sys
import io
from pathlib import Path

# Force UTF-8 encoding for Windows consoles to support rich symbols (checkmark, etc)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

# Ensure project root is in sys.path
project_root = Path(__file__).parent.absolute()
sys.path.append(str(project_root))

from framework.orchestrator.orchestrator import Orchestrator
from framework.core.config import Config, load_config

console = Console()


def _get_orchestrator(config_path: str | None = None) -> Orchestrator:
    """Helper to initialize orchestrator with config."""
    config = load_config(Path(config_path) if config_path else None)
    return Orchestrator(config)


@click.group()
def cli():
    """Agentic TestGen Framework (ATF) CLI."""
    pass


@cli.command("run")
@click.argument("prompt", required=False)
@click.option(
    "--jira",
    "jira_ticket_id",
    help="Jira ticket ID to use as test input (e.g. QA-123).",
)
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Run the generated tests with pytest after generation.",
)
@click.option(
    "--path",
    "test_path",
    help="Path to a specific test file or method to execute (e.g. tests/UI/test_file.py::test_func).",
)
@click.option(
    "--cicd",
    "generate_cicd",
    is_flag=True,
    default=False,
    help="Generate a CI/CD pipeline config after test generation.",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    metavar="PATH",
    help="Path to a custom config.yaml (default: configs/config.yaml).",
)
def run_command(
    prompt: str,
    jira_ticket_id: str | None,
    execute: bool,
    test_path: str | None,
    generate_cicd: bool,
    config_path: str | None,
) -> None:
    """Generate tests from a natural language PROMPT or Jira ticket."""
    if not prompt and not jira_ticket_id:
        console.print(
            "[bold red]Error:[/] Provide a PROMPT or use --jira TICKET_ID.",
        )
        sys.exit(1)

    if not prompt and jira_ticket_id:
        prompt = f"Generate tests for Jira ticket {jira_ticket_id}"

    _print_header(prompt, jira_ticket_id, execute, generate_cicd)

    try:
        orchestrator = _get_orchestrator(config_path)
    except Exception as exc:
        console.print(f"[bold red]Startup error:[/] {exc}")
        sys.exit(1)

    with console.status("[bold green]Running ATF pipeline...[/]", spinner="dots"):
        try:
            context = orchestrator.run(
                prompt=prompt,
                jira_ticket_id=jira_ticket_id,
                execute=execute,
                generate_cicd=generate_cicd,
                test_path=test_path,
            )
        except Exception as exc:
            console.print(f"\n[bold red]Pipeline failed:[/] {exc}")
            sys.exit(1)

    _print_results(context)


@cli.command("generate-cicd")
@click.option(
    "--config",
    "config_path",
    default=None,
    metavar="PATH",
    help="Path to a custom config.yaml.",
)
def generate_cicd_command(config_path: str | None) -> None:
    """Generate a CI/CD pipeline config for the current project."""
    from framework.core.base_agent import PipelineContext
    import uuid

    console.print(Panel("[bold cyan]Generating CI/CD pipeline config...[/]"))

    try:
        orchestrator = _get_orchestrator(config_path)
    except Exception as exc:
        console.print(f"[bold red]Startup error:[/] {exc}")
        sys.exit(1)

    context = PipelineContext(
        correlation_id=str(uuid.uuid4()),
        raw_prompt="generate CI/CD",
        intent="Generate CI/CD pipeline for existing test suite",
    )

    try:
        orchestrator._cicd_agent.run(context)
        console.print("[bold green]✓[/] CI/CD pipeline config generated.")
    except Exception as exc:
        console.print(f"[bold red]Failed:[/] {exc}")
        sys.exit(1)


def _print_header(
    prompt: str,
    jira_ticket_id: str | None,
    execute: bool,
    generate_cicd: bool,
) -> None:
    lines = [f"[bold]Prompt:[/] {prompt}"]
    if jira_ticket_id:
        lines.append(f"[bold]Jira Ticket:[/] {jira_ticket_id}")
    lines.append(f"[bold]Execute:[/] {'yes' if execute else 'no'}")
    lines.append(f"[bold]Generate CI/CD:[/] {'yes' if generate_cicd else 'no'}")
    console.print(Panel("\n".join(lines), title="[bold cyan]ATF Run[/]", expand=False))


def _print_results(context) -> None:
    """Pretty-print the pipeline results to the terminal."""
    console.print("\n[bold cyan]Pipeline summary[/bold cyan]\n")

    # Classification
    status_icon = "[bold green]✓[/]" if not context.pipeline_errors else "[bold yellow]![/]"
    console.print(
        f"{status_icon} Test Type: [cyan]{context.test_type}[/]  |  "
        f"Intent: {context.intent}"
    )

    # Scripts generated
    if context.generated_scripts:
        table = Table(title="Generated Scripts", box=box.ROUNDED)
        table.add_column("File", style="cyan")
        table.add_column("Type")
        for script in context.generated_scripts:
            table.add_row(script.filename, script.test_type)
        console.print(table)

    # Execution results
    if context.execution_result:
        er = context.execution_result
        colour = "green" if er.failed == 0 else "red"
        console.print(
            f"Execution: [{colour}]{er.passed}/{er.total} passed[/{colour}] "
            f"({er.failed} failed, {er.errors} errors) in {er.duration_seconds}s"
        )

    # Self-healing results
    if context.self_healing_results:
        healed_count = sum(1 for r in context.self_healing_results if r.get("healed_content"))
        console.print(
            f"Self-Healing: {len(context.self_healing_results)} failures analyzed, "
            f"[green]{healed_count} auto-fixes suggested[/green]"
        )
        for result in context.self_healing_results:
            cause = result.get("analysis", {}).get("root_cause", "Unknown cause")
            console.print(f" • [yellow]Fix for {result.get('filename')}:[/][italic] {cause}[/]")

    # Report path
    if context.report_path:
        console.print(
            f"\nReport: [bold blue]allure serve {context.report_path}[/bold blue]"
        )

    # Pipeline errors
    if context.pipeline_errors:
        console.print("\n[bold yellow]Pipeline warnings:[/]")
        for err in context.pipeline_errors:
            console.print(f"  [yellow]•[/] {err}")

    console.print()


if __name__ == "__main__":
    cli()
