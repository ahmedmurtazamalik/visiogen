import json
from pathlib import Path

import pytest

from visiogen import pipeline as pipeline_module
from visiogen.critic import CritiqueResult, VisualCritique, VisualIssue
from visiogen.design import DiagramDesign
from visiogen.designer import DesignMetadata, DesignResult
from visiogen.pipeline import HybridGenerationPipeline, PipelineError


def test_atomic_text_evidence_disables_newline_translation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "raw-response.json"
    raw_response = '{"answer":"ok"}\r\n \t'
    real_fdopen = pipeline_module.os.fdopen
    seen_newline = []

    def recording_fdopen(descriptor, *args, **kwargs):
        seen_newline.append(kwargs.get("newline"))
        return real_fdopen(descriptor, *args, **kwargs)

    monkeypatch.setattr(pipeline_module.os, "fdopen", recording_fdopen)

    pipeline_module._write_text(destination, raw_response)

    assert seen_newline == [""]
    assert destination.read_bytes() == raw_response.encode("utf-8")


def test_source_state_does_not_claim_an_ancestor_consumer_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    consumer = tmp_path / "consumer"
    installed_module = (
        consumer
        / ".venv"
        / "lib"
        / "python3.11"
        / "site-packages"
        / "visiogen"
        / "pipeline.py"
    )
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# installed wheel\n")
    (consumer / ".git").mkdir()

    monkeypatch.setattr(pipeline_module, "__file__", str(installed_module))

    def unrelated_repository(*args, **kwargs):
        return type(
            "Completed",
            (),
            {"stdout": "deadbeef\n", "returncode": 0},
        )()

    monkeypatch.setattr(pipeline_module.subprocess, "run", unrelated_repository)

    assert pipeline_module._source_state() == {
        "source_revision": None,
        "source_worktree_clean": None,
    }


def test_source_state_records_the_owning_source_checkout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "visiogen"
    source_module = repository / "src" / "visiogen" / "pipeline.py"
    source_module.parent.mkdir(parents=True)
    source_module.write_text("# source checkout\n")
    (repository / ".git").mkdir()
    calls = []

    monkeypatch.setattr(pipeline_module, "__file__", str(source_module))

    def own_repository(args, **kwargs):
        calls.append((args, kwargs))
        stdout = "abc123\n" if args[1:3] == ["rev-parse", "HEAD"] else ""
        return type("Completed", (), {"stdout": stdout, "returncode": 0})()

    monkeypatch.setattr(pipeline_module.subprocess, "run", own_repository)

    assert pipeline_module._source_state() == {
        "source_revision": "abc123",
        "source_worktree_clean": True,
    }
    assert len(calls) == 2
    assert all(call[1]["cwd"] == repository for call in calls)


def design_result() -> DesignResult:
    design = DiagramDesign.model_validate(
        {
            "graph": {
                "title": "Simple flow",
                "diagram_type": "flowchart",
                "orientation": "left_to_right",
                "nodes": [
                    {"id": "start", "type": "terminator", "label": "Start"},
                    {"id": "finish", "type": "terminator", "label": "Finish"},
                ],
                "edges": [
                    {
                        "id": "flow",
                        "source": "start",
                        "target": "finish",
                        "relation": "flow",
                        "direction": "forward",
                        "style": "solid",
                    }
                ],
            },
            "layout": {
                "composition": "compact_flow",
                "page_width": 8.0,
                "page_height": 4.0,
                "placements": [
                    {"node_id": "start", "x": 2.0, "y": 2.0, "width": 1.5, "height": 0.8},
                    {"node_id": "finish", "x": 6.0, "y": 2.0, "width": 1.5, "height": 0.8},
                ],
                "connector_hints": [{"edge_id": "flow"}],
            },
            "rationale": "Direct flow.",
        }
    )
    return DesignResult(
        design=design,
        raw_responses=(design.model_dump_json() + "  \n",),
        user_prompts=("Create a flow from start to finish\t",),
        transport_prompts=("Exact provider design prompt  \n",),
        metadata=DesignMetadata(attempts=1, request_ids=(), elapsed_ms=25.0),
    )


class FakeDesigner:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def design(self, text: str) -> DesignResult:
        self.requests.append(text)
        return design_result()


def test_pipeline_uses_ai_design_geometry_and_writes_provenance(tmp_path: Path) -> None:
    designer = FakeDesigner()
    render_calls = []
    validation_calls = []
    template = tmp_path / "template.vsdx"
    template.write_bytes(b"canonical-template")

    def render(template_path, layout, output_path):
        render_calls.append((template_path, layout, output_path))
        Path(output_path).write_bytes(b"native-visio-package")
        return Path(output_path)

    def validate(path):
        validation_calls.append(Path(path))

    output = tmp_path / "output.vsdx"
    debug = tmp_path / "run"
    pipeline = HybridGenerationPipeline(
        designer=designer,
        template_path=template,
        provider="codex",
        model="gpt-5.6-sol",
        render=render,
        validate_package=validate,
    )

    source_request = "Create a flow from start to finish  \n"
    result = pipeline.generate(
        source_request,
        output,
        artifact_dir=debug,
    )

    assert result.output_path == output
    assert output.read_bytes() == b"native-visio-package"
    assert designer.requests == [source_request]
    assert render_calls[0][1].graph.nodes[0].x == 2.0
    assert validation_calls == [output]
    assert (debug / "01-request.txt").read_text() == source_request
    assert (debug / "01-design-user-prompt-1.txt").read_text() == (
        "Create a flow from start to finish\t"
    )
    assert (debug / "02-provider-prompt-1.txt").read_text() == (
        "Exact provider design prompt  \n"
    )
    assert (debug / "02-design-response-1.json").read_text().endswith("  \n")
    raw = json.loads((debug / "02-design-response-1.json").read_text())
    assert raw["layout"]["composition"] == "compact_flow"
    validated = json.loads((debug / "03-validated-design.json").read_text())
    assert validated["layout"]["placements"][1]["x"] == 6.0
    manifest = json.loads((debug / "manifest.json").read_text())
    assert manifest["provider"] == "codex"
    assert manifest["model"] == "gpt-5.6-sol"
    assert manifest["design_attempts"] == 1
    assert manifest["output_sha256"]
    assert manifest["request_sha256"]
    assert manifest["template_sha256"]
    assert manifest["diagram_design_schema_sha256"]
    assert "source_revision" in manifest
    assert "source_worktree_clean" in manifest
    assert "02-provider-prompt-1.txt" in manifest["artifact_sha256"]


def test_pipeline_runs_one_image_critique_and_renders_valid_revision(tmp_path: Path) -> None:
    initial = design_result()
    revised = initial.design.model_copy(deep=True)
    revised.layout.placements[1].x = 6.5
    critique = VisualCritique(
        approved=False,
        summary="Increase separation between the terminators.",
        issues=[
            VisualIssue(
                severity="medium",
                category="spacing",
                description="The flow benefits from more breathing room.",
                node_ids=["start", "finish"],
                edge_ids=["flow"],
            )
        ],
        revised_design=revised,
    )

    class FakeCritic:
        def __init__(self) -> None:
            self.calls = []

        def critique(self, source_text, design, preview_path):
            self.calls.append((source_text, design, preview_path))
            return CritiqueResult(
                critique=critique,
                revised_design=revised,
                raw_response=critique.model_dump_json() + "\t\n",
                user_prompt="Exact critique request  ",
                transport_prompt="Exact provider critique prompt\t\n",
                elapsed_ms=40.0,
            )

    critic = FakeCritic()
    render_x = []
    preview_calls = 0

    def render(template_path, layout, output_path):
        finish_x = layout.graph.nodes[1].x
        render_x.append(finish_x)
        Path(output_path).write_bytes(f"vsdx-{finish_x}".encode())
        return Path(output_path)

    def preview(source, destination):
        nonlocal preview_calls
        preview_calls += 1
        Path(destination).write_bytes(b"real-preview")
        if preview_calls == 1:
            output.unlink()
            output.symlink_to(victim)
        return Path(destination)

    output = tmp_path / "output.vsdx"
    victim = tmp_path / "victim.vsdx"
    victim.write_bytes(b"keep")
    debug = tmp_path / "run"
    pipeline = HybridGenerationPipeline(
        designer=FakeDesigner(),
        template_path=tmp_path / "template.vsdx",
        provider="codex",
        model="gpt-5.6-sol",
        render=render,
        validate_package=lambda path: None,
        critic=critic,
        export_preview=preview,
    )

    pipeline.generate("Create a flow", output, artifact_dir=debug)

    assert render_x == [6.0, 6.5]
    assert not output.is_symlink()
    assert output.read_bytes() == b"vsdx-6.5"
    assert victim.read_bytes() == b"keep"
    assert (debug / "05-initial.vsdx").read_bytes() == b"vsdx-6.0"
    assert (debug / "06-initial-preview.png").is_file()
    assert (debug / "08-critique-response.json").is_file()
    assert (debug / "07-critique-user-prompt.txt").read_text() == (
        "Exact critique request  "
    )
    assert (debug / "07-critique-provider-prompt.txt").read_text() == (
        "Exact provider critique prompt\t\n"
    )
    assert (debug / "08-critique-response.json").read_text().endswith("\t\n")
    assert (debug / "09-revised-design.json").is_file()
    assert (debug / "10-revised.vsdx").read_bytes() == b"vsdx-6.5"
    assert (debug / "11-final-preview.png").is_file()
    assert len(critic.calls) == 1
    manifest = json.loads((debug / "manifest.json").read_text())
    assert manifest["visual_critique_performed"] is True
    assert manifest["visual_critique_approved_initial"] is False
    assert manifest["revision_applied"] is True


def test_pipeline_refuses_nonempty_evidence_directory(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "victim.txt").write_text("keep me")
    pipeline = HybridGenerationPipeline(
        designer=FakeDesigner(),
        template_path=tmp_path / "template.vsdx",
        provider="codex",
        model="gpt-5.6-sol",
        render=lambda *args: pytest.fail("render must not run"),
        validate_package=lambda path: None,
    )

    with pytest.raises(PipelineError, match="must be empty"):
        pipeline.generate(
            "Create a flow",
            tmp_path / "output.vsdx",
            artifact_dir=evidence,
        )

    assert (evidence / "victim.txt").read_text() == "keep me"


@pytest.mark.parametrize("reserved_name", ["manifest.json", "manifest.json.tmp"])
def test_pipeline_refuses_output_collision_with_evidence_file(
    tmp_path: Path,
    reserved_name: str,
) -> None:
    evidence = tmp_path / "evidence"
    pipeline = HybridGenerationPipeline(
        designer=FakeDesigner(),
        template_path=tmp_path / "template.vsdx",
        provider="codex",
        model="gpt-5.6-sol",
        render=lambda *args: pytest.fail("render must not run"),
        validate_package=lambda path: None,
    )

    with pytest.raises(PipelineError, match="reserved evidence filename"):
        pipeline.generate(
            "Create a flow",
            evidence / reserved_name,
            artifact_dir=evidence,
        )


def test_pipeline_rejects_renderer_returning_a_different_path(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"

    def misdirected_render(template, layout, output):
        wrong = evidence / "manifest.json.tmp"
        wrong.write_bytes(b"not-the-requested-output")
        return wrong

    pipeline = HybridGenerationPipeline(
        designer=FakeDesigner(),
        template_path=tmp_path / "template.vsdx",
        provider="codex",
        model="gpt-5.6-sol",
        render=misdirected_render,
        validate_package=lambda path: None,
    )

    with pytest.raises(PipelineError, match="unexpected output path"):
        pipeline.generate(
            "Create a flow",
            tmp_path / "output.vsdx",
            artifact_dir=evidence,
        )

    assert not (evidence / "manifest.json").exists()
