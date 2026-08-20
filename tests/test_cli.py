from pathlib import Path
from typing import Any, cast

import pytest

from visiogen.cli import main
from visiogen.pipeline import GenerationResult, PipelineError


class FakePipeline:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, text, output, *, artifact_dir):
        self.calls.append((text, Path(output), Path(artifact_dir)))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"vsdx")
        return GenerationResult(
            output_path=Path(output),
            artifact_dir=Path(artifact_dir),
            provider="codex",
            model="gpt-5.6-sol",
        )


def template_file(tmp_path: Path) -> Path:
    template = tmp_path / "template.vsdx"
    template.write_bytes(b"template")
    return template


def test_generate_command_runs_hybrid_pipeline_with_explicit_artifacts(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    factory_calls = []

    def factory(settings, template_path, *, enable_critique):
        factory_calls.append((settings, Path(template_path), enable_critique))
        return pipeline

    output = tmp_path / "drawing.vsdx"
    artifacts = tmp_path / "evidence"
    template = template_file(tmp_path)
    exit_code = main(
        [
            "generate",
            "--text",
            "Create a sensor system",
            "--output",
            str(output),
            "--artifact-dir",
            str(artifacts),
            "--template",
            str(template),
        ],
        pipeline_factory=factory,
    )

    assert exit_code == 0
    assert pipeline.calls == [("Create a sensor system", output, artifacts)]
    assert factory_calls[0][0].provider == "codex"
    assert factory_calls[0][0].codex_model == "gpt-5.6-sol"
    assert factory_calls[0][2] is True


def test_generate_command_accepts_input_file_and_no_critique(tmp_path: Path) -> None:
    request = tmp_path / "request.txt"
    request.write_text("Create a flow\n")
    pipeline = FakePipeline()
    template = template_file(tmp_path)

    exit_code = main(
        [
            "generate",
            "--input-file",
            str(request),
            "--output",
            str(tmp_path / "drawing.vsdx"),
            "--artifact-dir",
            str(tmp_path / "evidence"),
            "--no-critique",
            "--template",
            str(template),
        ],
        pipeline_factory=lambda settings, template, *, enable_critique: (
            pipeline if not enable_critique else pytest.fail("critique should be disabled")
        ),
    )

    assert exit_code == 0
    assert pipeline.calls[0][0] == "Create a flow\n"


def test_generate_requires_exactly_one_text_source(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "generate",
                "--output",
                str(tmp_path / "drawing.vsdx"),
                "--artifact-dir",
                str(tmp_path / "evidence"),
            ]
        )


def test_generate_reports_missing_input_file_cleanly(tmp_path: Path, capsys) -> None:
    template = template_file(tmp_path)

    with pytest.raises(SystemExit) as error:
        main(
            [
                "generate",
                "--input-file",
                str(tmp_path / "missing.txt"),
                "--output",
                str(tmp_path / "drawing.vsdx"),
                "--artifact-dir",
                str(tmp_path / "evidence"),
                "--template",
                str(template),
            ]
        )

    assert error.value.code == 2
    assert "Could not read input file" in capsys.readouterr().err


def test_generate_reports_missing_template_cleanly(tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "generate",
                "--text",
                "Create a flow",
                "--output",
                str(tmp_path / "drawing.vsdx"),
                "--artifact-dir",
                str(tmp_path / "evidence"),
                "--template",
                str(tmp_path / "missing.vsdx"),
            ]
        )

    assert error.value.code == 2
    assert "Template file was not found" in capsys.readouterr().err


def test_generate_reports_pipeline_failures_cleanly(tmp_path: Path, capsys) -> None:
    class FailingPipeline:
        def generate(self, *args, **kwargs):
            raise PipelineError("Evidence directory must be empty")

    def factory(*args, **kwargs):
        return FailingPipeline()

    with pytest.raises(SystemExit) as error:
        main(
            [
                "generate",
                "--text",
                "Create a flow",
                "--output",
                str(tmp_path / "drawing.vsdx"),
                "--artifact-dir",
                str(tmp_path / "evidence"),
                "--template",
                str(template_file(tmp_path)),
            ],
            pipeline_factory=cast(Any, factory),
        )

    assert error.value.code == 2
    assert "Generation failed: Evidence directory must be empty" in capsys.readouterr().err
