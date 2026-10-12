import pytest

from testquality.cli import SUBCOMMANDS, build_parser, main


def test_no_args_prints_help(capsys):
    assert main([]) == 0
    assert "testquality" in capsys.readouterr().out


@pytest.mark.parametrize("name", sorted(SUBCOMMANDS))
def test_stub_subcommand_exits_2(name, capsys):
    assert main([name]) == 2
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
