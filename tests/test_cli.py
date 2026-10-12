import pytest

from testquality.cli import IMPLEMENTED, SUBCOMMANDS, build_parser, main


def test_no_args_prints_help(capsys):
    assert main([]) == 0
    assert "testquality" in capsys.readouterr().out


def test_every_subcommand_has_a_handler():
    assert set(SUBCOMMANDS) == set(IMPLEMENTED)


@pytest.mark.parametrize("name", sorted(SUBCOMMANDS))
def test_unimplemented_dispatch_exits_2(name, capsys, monkeypatch):
    monkeypatch.setattr("testquality.cli.IMPLEMENTED", {})
    needs_suite = {"execute", "coverage", "mutate", "traceability", "smells", "relevance"}
    argv = [name, "--suite", "x"] if name in needs_suite else [name]
    assert main(argv) == 2
    assert "not implemented" in capsys.readouterr().err


def test_unknown_subcommand_errors():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["nope"])
    assert exc.value.code == 2


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "testquality" in capsys.readouterr().out
