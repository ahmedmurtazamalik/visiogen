# Visiogen Documentation

The repository root contains only the product README. Detailed documentation is
organized here by purpose.

## Current architecture

- [System overview](architecture/SYSTEM_OVERVIEW.md)
- [Text-to-VSDX hybrid architecture](architecture/HYBRID_AI.md)
- [Generation v2 implementation plan](plans/active/GENERATION_V2.md)
- [Generation v2 quality evaluation contract](generation/GENERATION_V2_EVALUATION.md)
- [Generation v2 diagram specification](generation/DIAGRAM_SPECIFICATION.md)
- [Generation v2 analysis import](generation/ANALYSIS_IMPORT.md)
- [Generation v2 construction plan](generation/CONSTRUCTION_PLAN.md)
- [Generation v2 compiler IR](generation/COMPILER_IR.md)

## Analysis contracts and completed plan

- [Document-to-diagram analysis](plans/active/DOCUMENT_ANALYSIS.md)
- [Frozen document-analysis MVP contract](analysis/MVP_CONTRACT.md)
- [Deterministic PDF/DOCX ingestion](analysis/DOCUMENT_INGESTION.md)
- [Diagram discovery and image preparation](analysis/DIAGRAM_DISCOVERY.md)
- [Visual observation and semantic reconstruction](analysis/VISUAL_SEMANTICS.md)
- [Faithful textual description](analysis/FAITHFUL_DESCRIPTION.md)
- [Text claims and entity alignment](analysis/TEXT_CLAIMS_AND_ALIGNMENT.md)
- [Consistency analysis and findings](analysis/CONSISTENCY_ANALYSIS.md)
- [A8 held-out release evaluation](analysis/A8_RELEASE_EVALUATION.md)
- [A8 supported scope and known limitations](analysis/A8_SUPPORTED_SCOPE.md)

## Development

- [Parallel workstream boundaries](development/WORKSTREAMS.md)
- [Release checkpoints and repeatable A8 reruns](development/RELEASE_CHECKPOINTS.md)
- [Visio template catalog](../templates/TEMPLATE.md)

## Releases

- [Visiogen 0.1.0 experimental release candidate](releases/0.1.0-experimental.md)

## Acceptance

- [G3 AI construction planner](acceptance/G3_CONSTRUCTION_PLANNER.md)
- [G0 Generation v2 baseline and contract freeze](acceptance/G0_GENERATION_V2_BASELINE.md)
- [A8 deterministic hardening acceptance](acceptance/A8_HARDENING.md)
- [A8 AI-assisted release acceptance](acceptance/A8_AI_ASSISTED_ACCEPTANCE.md)
- [A0–A7 completeness audit](acceptance/A0_A7_COMPLETENESS_AUDIT.md)
- [A2 diagram discovery acceptance](acceptance/A2_DIAGRAM_DISCOVERY.md)
- [A3 visual semantics acceptance](acceptance/A3_VISUAL_SEMANTICS.md)
- [A4 faithful description acceptance](acceptance/A4_FAITHFUL_DESCRIPTION.md)
- [A5 text claims and alignment acceptance](acceptance/A5_TEXT_CLAIMS.md)
- [A6 consistency engine acceptance](acceptance/A6_CONSISTENCY.md)
- [A7 vertical analysis pipeline acceptance](acceptance/A7_VERTICAL_PIPELINE.md)
- [Hybrid-AI verification record](acceptance/HYBRID_AI.md)
- [Windows and native Visio procedure](acceptance/WINDOWS_VISIO.md)

Historical milestone reports live under `acceptance/archive/`. Superseded
implementation plans live under `plans/archive/`; they are retained for provenance
and must not be treated as current architecture.
