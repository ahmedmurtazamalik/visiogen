from visiogen.cli import build_parser, main


def test_help_exits_successfully(capsys):
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("help did not exit")

    assert "Generate editable Visio diagrams" in capsys.readouterr().out


def test_cli_uses_visiogen_program_name():
    assert build_parser().prog == "visiogen"
