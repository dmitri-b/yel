"""Rich-powered terminal output helpers for the CLI."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


def status(message: str, *, style: str = "cyan") -> None:
    """Print a styled runtime status line to stderr."""
    err_console.print(Text(message, style=style))


def error(message: str) -> None:
    """Print a styled error line to stderr."""
    status(message, style="bold red")


def print_devices_table(
    devices: Iterable[dict[str, Any]],
    *,
    default_in: int | None,
    default_out: int | None,
) -> None:
    """Render audio devices in a scannable table."""
    table = Table(
        title="Audio devices",
        box=box.SIMPLE_HEAD,
        show_lines=False,
        title_style="bold",
        header_style="bold cyan",
    )
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Device")
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("Default", no_wrap=True)

    for idx, dev in enumerate(devices):
        ins = int(dev["max_input_channels"])
        outs = int(dev["max_output_channels"])
        defaults = []
        if idx == default_in and ins:
            defaults.append("input")
        if idx == default_out and outs:
            defaults.append("output")
        table.add_row(
            str(idx),
            str(dev["name"]),
            str(ins),
            str(outs),
            ", ".join(defaults) or "-",
        )

    console.print(table)


def print_settings_table(rows: Iterable[tuple[str, object]]) -> None:
    """Render resolved configuration as a table."""
    table = Table(
        title="Resolved configuration",
        box=box.SIMPLE_HEAD,
        title_style="bold",
        header_style="bold cyan",
    )
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value")

    for key, value in rows:
        table.add_row(key, repr(value))

    console.print(table)


def print_path_status(path: Path, *, found: bool) -> None:
    """Render the resolved .env path status."""
    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
    table.add_column("Config file")
    table.add_column("Status", no_wrap=True)
    table.add_row(str(path), "found" if found else "not found")
    console.print(table)


def print_check(name: str, *, ok: bool, detail: str) -> None:
    """Render one doctor check."""
    label = "ok" if ok else "fail"
    style = "green" if ok else "bold red"
    console.print(
        Text.assemble((f"{label:>4}", style), "  ", (name, "bold"), f"  {detail}")
    )
