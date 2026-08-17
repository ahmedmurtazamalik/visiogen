from vega.cli import main


def test_help_exits_successfully(capsys):
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("help did not exit")

    assert "Generate editable Visio diagrams" in capsys.readouterr().out
