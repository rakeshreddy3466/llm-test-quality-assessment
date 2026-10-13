"""Interactive manual-review rating (`testquality review rate`).

Reads ONLY manual_review/sample_blinded.csv. It never reads the origin key or any automatic
score, never suggests a rating and never fills one in: every value comes from the rater.
Progress is saved after every item, so the session can be stopped and resumed.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Callable
from pathlib import Path

SCALES = ["relevance", "clarity", "maintainability", "oracle_strength"]
PROMPTS = {
    "relevance": "Relevance (1-5)",
    "clarity": "Clarity of purpose (1-5)",
    "maintainability": "Maintainability (1-5)",
    "oracle_strength": "Oracle strength (1-5)",
}
QUIT = "q"


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [{k: (v or "") for k, v in r.items() if k is not None}
                for r in csv.DictReader(fh)]


def is_rated(row: dict) -> bool:
    return all(row.get(s, "").strip() in {"1", "2", "3", "4", "5"} for s in SCALES)


def load_state(blinded: Path, rated: Path) -> list[dict]:
    """Rows of the blinded sample in item_id order, with earlier ratings merged in."""
    rows = sorted(read_rows(blinded), key=lambda r: r["item_id"])
    if rated.exists():
        done = {r["item_id"]: r for r in read_rows(rated)}
        for r in rows:
            prev = done.get(r["item_id"])
            if prev and is_rated(prev):
                for col in (*SCALES, "notes"):
                    r[col] = prev.get(col, "")
    return rows


def save(rated: Path, rows: list[dict], fields: list[str]) -> None:
    tmp = rated.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, rated)


def ask_int(prompt: str, input_fn: Callable[[str], str], echo: Callable[[str], None]) -> int | None:
    """Ask until the answer is an integer 1-5. Returns None if the rater types 'q'."""
    while True:
        answer = input_fn(f"{prompt}: ").strip().lower()
        if answer == QUIT:
            return None
        if answer in {"1", "2", "3", "4", "5"}:
            return int(answer)
        echo("  please enter an integer from 1 to 5 (or q to save and quit)")


def show_item(console, row: dict, position: int, total: int) -> None:
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.syntax import Syntax

    console.clear()
    console.print(Rule(f"[bold]{position}/{total}[/bold]   {row['item_id']}   {row['test_name']}"))
    console.print(Syntax(row["test_code"], "python", theme="monokai", word_wrap=True))
    if row.get("context_code", "").strip():
        console.print(Panel(
            Syntax(row["context_code"], "python", theme="monokai", word_wrap=True),
            title="context (helpers / fixtures used by the test)", border_style="dim",
        ))


def run(
    blinded: Path, rated: Path, *, input_fn: Callable[[str], str] = input,
    console=None, clear: bool = True,
) -> tuple[int, int]:
    """Rate the unrated items. Returns (rated count, total)."""
    from rich.console import Console

    console = console or Console()
    rows = load_state(blinded, rated)
    fields = list(read_rows(blinded)[0].keys()) if rows else []
    total = len(rows)
    pending = [r for r in rows if not is_rated(r)]
    if not pending:
        console.print(f"All {total} items are already rated ({rated}).")
        return total, total
    console.print(f"{total - len(pending)}/{total} already rated; "
                  f"enter 1-5 per scale, 'q' to save and quit.")
    for row in pending:
        position = rows.index(row) + 1
        if clear:
            show_item(console, row, position, total)
        else:
            console.print(f"{position}/{total}  {row['item_id']}  {row['test_name']}")
        values: dict[str, int] = {}
        for scale in SCALES:
            v = ask_int(PROMPTS[scale], input_fn, console.print)
            if v is None:  # quit: the half-rated item is discarded, others are saved
                done = sum(is_rated(r) for r in rows)
                save(rated, rows, fields)
                console.print(f"Saved. {done}/{total} rated. Run the command again to resume.")
                return done, total
            values[scale] = v
        note = input_fn("Note (optional, Enter to skip): ").strip()
        for scale, v in values.items():
            row[scale] = str(v)
        row["notes"] = note
        save(rated, rows, fields)  # after every item
        console.print(f"  saved {sum(is_rated(r) for r in rows)}/{total}")
    console.print(f"Done: {total}/{total} rated -> {rated}")
    return total, total
