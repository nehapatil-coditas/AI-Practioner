"""actiontrack CLI — wires the four commands to their implementations."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from actiontrack.commands.done import ItemNotFoundError, mark_done
from actiontrack.commands.followup import FollowupError, run_followup
from actiontrack.commands.ingest import IngestError, run_ingest
from actiontrack.commands.list_cmd import ListError, list_items

app = typer.Typer(
    name="actiontrack",
    help="Track action items from meeting notes and draft follow-up emails.",
    no_args_is_help=True,
)
console = Console()


def _project_dir() -> Path:
    return Path.cwd()


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter(f"expected YYYY-MM-DD, got {value!r}") from exc


@app.command()
def ingest(folder: Path = typer.Argument(..., help="Folder of .md meeting notes to ingest")) -> None:
    """Parse every .md note in FOLDER, track action items, report a summary."""
    try:
        summary = run_ingest(folder, _project_dir())
    except IngestError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"Files processed: {summary.files_processed}")
    console.print(f"New items: {summary.items_new}")
    console.print(f"Duplicate occurrences merged: {summary.occurrences_merged}")

    if summary.files_skipped:
        console.print(f"\n[yellow]Skipped {len(summary.files_skipped)} malformed file(s):[/yellow]")
        for skipped in summary.files_skipped:
            console.print(f"  - {skipped.filename}: {skipped.reason}")

    if summary.ambiguous_owners:
        console.print(f"\n[yellow]{len(summary.ambiguous_owners)} item(s) with ambiguous owner:[/yellow]")
        for flagged in summary.ambiguous_owners:
            console.print(f"  - {flagged.description} ({flagged.source_file})")

    if summary.unassigned_owners:
        console.print(f"\n[yellow]{len(summary.unassigned_owners)} item(s) with no owner:[/yellow]")
        for flagged in summary.unassigned_owners:
            console.print(f"  - {flagged.description} ({flagged.source_file})")

    if summary.unresolved_due_dates:
        console.print(f"\n[yellow]{len(summary.unresolved_due_dates)} item(s) with unresolved due date:[/yellow]")
        for flagged in summary.unresolved_due_dates:
            console.print(f"  - {flagged.description} ({flagged.source_file})")


@app.command(name="list")
def list_cmd(
    owner: Optional[str] = typer.Option(None, "--owner", help="Filter by owner"),
    status: Optional[str] = typer.Option(None, "--status", help="open | done | overdue"),
    due_before: Optional[str] = typer.Option(None, "--due-before", help="YYYY-MM-DD"),
) -> None:
    """List stored action items, optionally filtered."""
    due_before_date = _parse_date(due_before) if due_before else None

    try:
        items = list_items(_project_dir(), owner=owner, status=status, due_before=due_before_date)
    except ListError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if not items:
        console.print("No matching items. (Run 'actiontrack ingest <folder>' first if you haven't.)")
        return

    table = Table()
    for column in ("ID", "Owner", "Task", "Due Date", "Status", "Source File(s)"):
        table.add_column(column)
    for item in items:
        table.add_row(str(item.id), item.owner, item.task, item.due_date, item.status, item.source_files)
    console.print(table)


@app.command()
def done(item_id: int = typer.Argument(..., help="ID of the item to mark done")) -> None:
    """Mark an action item as done."""
    try:
        item = mark_done(_project_dir(), item_id)
    except ItemNotFoundError:
        console.print(f"[red]Error:[/red] no item with id {item_id}")
        raise typer.Exit(code=1)

    console.print(f"[green]Marked done:[/green] #{item.id} {item.owner or '(unassigned)'} — {item.task}")


@app.command()
def followup(
    owner: Optional[str] = typer.Argument(None, help="Owner to draft a follow-up email for"),
    all_: bool = typer.Option(False, "--all", help="Draft follow-ups for every owner with open/overdue items"),
) -> None:
    """Draft (never send) a follow-up email summarizing open/overdue items."""
    try:
        results = run_followup(_project_dir(), owner=owner, all_owners=all_)
    except FollowupError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    for result in results:
        if result.outcome == "drafted":
            console.print(f"[green]Draft created[/green] for {result.owner} ({result.draft_ref})")
        elif result.outcome == "skipped_no_items":
            console.print(f"[dim]Skipped {result.owner}: nothing to follow up on[/dim]")
        elif result.outcome == "skipped_no_email":
            console.print(f"[yellow]Skipped {result.owner}: {result.detail}[/yellow]")
        else:
            console.print(f"[red]Failed[/red] for {result.owner}: {result.detail}")


if __name__ == "__main__":
    app()
