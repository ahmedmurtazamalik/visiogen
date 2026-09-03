import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from visiogen.cli import main
from visiogen.pipeline import GenerationResult, PipelineError
from visiogen.generation.specification import DiagramSpecification


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


def test_generate_command_accepts_validated_spec_file(tmp_path: Path) -> None:
    specification = {
        "version": 1,
        "title": "Simple flow",
        "purpose": "Show a direct flow.",
        "audience": "Reviewers",
        "diagram_type": "flowchart",
        "notation": "flowchart",
        "orientation": "left_to_right",
        "primary_flow": "start to finish",
        "objects": [
            {"id": "start", "label": "Start", "type": "terminator"},
            {"id": "finish", "label": "Finish", "type": "terminator"},
        ],
        "relationships": [
            {"id": "flow", "source": "start", "target": "finish"}
        ],
        "visual_requirements": [
            {"id": "clear_labels", "description": "Labels remain readable."}
        ],
        "forbidden_conditions": ["No overlapping shapes."],
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(specification))
    pipeline = FakePipeline()

    assert main(
        [
            "generate",
            "--spec-file",
            str(path),
            "--output",
            str(tmp_path / "drawing.vsdx"),
            "--artifact-dir",
            str(tmp_path / "evidence"),
            "--template",
            str(template_file(tmp_path)),
        ],
        pipeline_factory=lambda *args, **kwargs: pipeline,
    ) == 0

    assert isinstance(pipeline.calls[0][0], DiagramSpecification)


def test_generate_can_stop_after_analysis_specification(tmp_path: Path) -> None:
    output = tmp_path / "draft.json"

    def unexpected_factory(*args, **kwargs):
        pytest.fail("pipeline must not be constructed when stopping after specification")

    assert main(
        [
            "generate",
            "--analysis-bundle",
            "tests/fixtures/generation_v2/analysis_bundles/docx",
            "--stop-after-specification",
            "--output",
            str(output),
        ],
        pipeline_factory=cast(Any, unexpected_factory),
    ) == 0

    specification = DiagramSpecification.model_validate_json(output.read_bytes())
    assert specification.source is not None
    assert specification.source.document_kind == "docx"


def test_generate_passes_analysis_specification_to_pipeline(tmp_path: Path) -> None:
    pipeline = FakePipeline()

    assert main(
        [
            "generate",
            "--analysis-bundle",
            "tests/fixtures/generation_v2/analysis_bundles/pdf",
            "--output",
            str(tmp_path / "drawing.vsdx"),
            "--artifact-dir",
            str(tmp_path / "evidence"),
            "--template",
            str(template_file(tmp_path)),
        ],
        pipeline_factory=lambda *args, **kwargs: pipeline,
    ) == 0

    source = pipeline.calls[0][0]
    assert isinstance(source, DiagramSpecification)
    assert source.source is not None
    assert source.source.document_kind == "pdf"


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


class FakeAnalysisPipeline:
    def __init__(self, *, status: str = "complete") -> None:
        self.status = status
        self.calls = []

    def analyze(self, source, artifact_dir, *, options, progress=None):
        artifacts = Path(artifact_dir).resolve()
        artifacts.mkdir(parents=True)
        (artifacts / "report.md").write_text("# Analysis\n")
        self.calls.append((Path(source), Path(artifact_dir), options))
        if progress is not None:
            from visiogen.analysis.pipeline import AnalysisProgress

            progress(
                AnalysisProgress(
                    stage="candidate_start",
                    message="starting candidate analysis",
                    candidate_id="candidate-0001",
                    candidate_index=1,
                    candidate_total=1,
                )
            )
        return SimpleNamespace(
            artifact_dir=artifacts,
            analysis=SimpleNamespace(status=self.status),
        )


def test_analyze_command_publishes_report_and_passes_scoped_options(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "design.pdf"
    source.write_bytes(b"%PDF fixture")
    output = tmp_path / "report.md"
    artifacts = tmp_path / "evidence"
    pipeline = FakeAnalysisPipeline()
    factory_calls = []

    def factory(settings):
        factory_calls.append(settings)
        return pipeline

    exit_code = main(
        [
            "analyze",
            "--input",
            str(source),
            "--output",
            str(output),
            "--artifact-dir",
            str(artifacts),
            "--page",
            "2",
            "--max-diagrams",
            "3",
            "--strict-coverage",
            "--no-consistency-check",
        ],
        analysis_pipeline_factory=factory,
    )

    assert exit_code == 0
    assert output.read_text() == "# Analysis\n"
    assert factory_calls[0].provider == "codex"
    assert factory_calls[0].codex_model == "gpt-5.6-sol"
    options = pipeline.calls[0][2]
    assert options.page_number == 2
    assert options.max_diagrams == 3
    assert options.strict_coverage
    assert not options.consistency_check
    assert "[candidate-0001 1/1] starting candidate analysis" in capsys.readouterr().err


def test_analyze_command_quiet_suppresses_progress(tmp_path: Path, capsys) -> None:
    source = tmp_path / "design.pdf"
    source.write_bytes(b"%PDF fixture")
    pipeline = FakeAnalysisPipeline()

    exit_code = main(
        [
            "analyze",
            "--input",
            str(source),
            "--output",
            str(tmp_path / "report.md"),
            "--artifact-dir",
            str(tmp_path / "evidence"),
            "--quiet",
        ],
        analysis_pipeline_factory=lambda settings: pipeline,
    )

    assert exit_code == 0
    assert "[visiogen" not in capsys.readouterr().err


def test_analyze_command_returns_distinct_partial_exit_code(tmp_path: Path) -> None:
    source = tmp_path / "design.docx"
    source.write_bytes(b"PK fixture")
    pipeline = FakeAnalysisPipeline(status="partial")

    exit_code = main(
        [
            "analyze",
            "--input",
            str(source),
            "--output",
            str(tmp_path / "report.md"),
            "--artifact-dir",
            str(tmp_path / "evidence"),
        ],
        analysis_pipeline_factory=lambda settings: pipeline,
    )

    assert exit_code == 3


def test_analyze_refuses_public_report_inside_private_evidence(tmp_path: Path, capsys) -> None:
    source = tmp_path / "design.pdf"
    source.write_bytes(b"%PDF fixture")
    artifacts = tmp_path / "evidence"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "analyze",
                "--input",
                str(source),
                "--output",
                str(artifacts / "report.md"),
                "--artifact-dir",
                str(artifacts),
            ],
            analysis_pipeline_factory=lambda settings: pytest.fail("must not build pipeline"),
        )

    assert error.value.code == 2
    assert "outside the private artifact directory" in capsys.readouterr().err


def test_analyze_refuses_private_evidence_nested_under_report_path(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "design.pdf"
    source.write_bytes(b"%PDF fixture")
    output = tmp_path / "report.md"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "analyze",
                "--input",
                str(source),
                "--output",
                str(output),
                "--artifact-dir",
                str(output / "evidence"),
            ],
            analysis_pipeline_factory=lambda settings: pytest.fail("must not build pipeline"),
        )

    assert error.value.code == 2
    assert "must not be nested beneath" in capsys.readouterr().err
