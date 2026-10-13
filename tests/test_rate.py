import csv
import inspect
from pathlib import Path

from rich.console import Console

from testquality import rate

FIELDS = ["item_id", "test_name", "test_code", "context_code", *rate.SCALES, "notes"]


def make_sample(path: Path, n: int = 3) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for i in range(n, 0, -1):  # deliberately unordered
            w.writerow({"item_id": f"R{i:02d}", "test_name": f"test_{i}",
                        "test_code": f"def test_{i}():\n    assert {i}\n", "context_code": "",
                        **{s: "" for s in rate.SCALES}, "notes": ""})


def scripted(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def console():
    return Console(file=open("/dev/null", "w"), force_terminal=False)


def test_rates_in_item_order_and_validates(tmp_path):
    blinded, rated = tmp_path / "b.csv", tmp_path / "r.csv"
    make_sample(blinded, 2)
    answers = ["0", "6", "x", "", "3", "4", "5", "1", "a note",   # R01 (invalid ones re-asked)
               "2", "2", "2", "2", ""]                              # R02
    got = rate.run(blinded, rated, input_fn=scripted(answers), console=console(), clear=False)
    assert got == (2, 2)
    rows = {r["item_id"]: r for r in rate.read_rows(rated)}
    assert [rows["R01"][s] for s in rate.SCALES] == ["3", "4", "5", "1"]
    assert rows["R01"]["notes"] == "a note"
    assert [rows["R02"][s] for s in rate.SCALES] == ["2", "2", "2", "2"]
    assert list(rows) == ["R01", "R02"]


def test_quit_saves_and_resume_skips_rated(tmp_path):
    blinded, rated = tmp_path / "b.csv", tmp_path / "r.csv"
    make_sample(blinded, 3)
    # rate R01 fully, start R02 then quit
    done, total = rate.run(blinded, rated, console=console(), clear=False,
                           input_fn=scripted(["5", "4", "3", "2", "", "1", "q"]))
    assert (done, total) == (1, 3)
    assert rate.is_rated({r["item_id"]: r for r in rate.read_rows(rated)}["R01"])
    asked = []

    def fn(prompt):
        asked.append(prompt)
        return "3" if "Note" not in prompt else ""

    done, total = rate.run(blinded, rated, input_fn=fn, console=console(), clear=False)
    assert (done, total) == (3, 3)
    assert len(asked) == 2 * 5  # only R02 and R03 were asked again (4 scales + note each)
    rows = {r["item_id"]: r for r in rate.read_rows(rated)}
    assert rows["R01"]["relevance"] == "5"  # earlier rating preserved


def test_saves_after_every_item(tmp_path):
    blinded, rated = tmp_path / "b.csv", tmp_path / "r.csv"
    make_sample(blinded, 2)
    seen = []

    def fn(prompt):
        if rated.exists():
            seen.append(sum(rate.is_rated(r) for r in rate.read_rows(rated)))
        return "" if "Note" in prompt else "4"

    rate.run(blinded, rated, input_fn=fn, console=console(), clear=False)
    assert max(seen) >= 1  # item 1 was on disk while item 2 was being rated


def test_blinding_no_access_to_key_or_scores():
    src = inspect.getsource(rate)
    code = src.split('"""', 2)[2]  # drop the module docstring
    for forbidden in ("key_do_not_open", "rq2_auto", "origin", "results/"):
        assert forbidden not in code
