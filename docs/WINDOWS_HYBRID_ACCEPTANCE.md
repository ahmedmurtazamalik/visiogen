# Windows Hybrid-AI and Native Visio Acceptance

This is the authoritative execution procedure for hybrid milestones H8–H10. It must run on Windows with desktop Microsoft Visio. Linux ZIP/XML checks and non-Visio rendering cannot replace it.

## What the Windows corpus proves

The corpus runner executes three fresh production-provider cases:

1. a branching order-fulfillment flowchart;
2. a contained IoT system architecture;
3. a contained smart-camera component schematic with reference callouts.

For each case it performs the complete bounded architecture:

```text
request
→ Codex structured design
→ hard validation and at most one design repair
→ hybrid layout
→ native VSDX render
→ Microsoft Visio PNG export
→ real multimodal critique
→ at most one validated revision and rerender
→ native Visio open/move/save/close/reopen acceptance
```

The runner refuses dirty source, refuses to merge with an existing output directory, and requires every manifest to record the exact source revision, clean state, and `visual_critique_performed: true`. A failed run is preserved under a timestamped `.failed-*` directory for diagnosis.

## Prerequisites

- Windows 10 or 11.
- Desktop Microsoft Visio installed and licensed.
- Git, Python 3.11+, and `uv` available on `PATH`.
- Codex CLI installed, authenticated, and available as `codex` on `PATH`.
- A clean checkout of Visiogen `main`.
- Network/provider quota sufficient for up to two structured design calls and one visual-critic call per case. A valid first design normally uses one design call; the second is only the bounded repair.

Verify the checkout in PowerShell:

```powershell
git pull --ff-only
git status --short --branch
git rev-parse HEAD
uv sync --frozen --extra dev
uv run pytest -q
codex --version
```

Do not continue if `git status --porcelain` reports modified or untracked files inside the repository.

## Run the complete corpus

From the repository root, choose a new output path that does not already exist:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\scripts\run_windows_hybrid_corpus.ps1 `
  -OutputDirectory "C:\VisiogenAcceptance\hybrid-$(git rev-parse --short HEAD)" `
  -Model "gpt-5.6-sol" `
  -Visible
```

`-Visible` keeps Microsoft Visio visible while the automation opens, exports, moves, saves, closes, and reopens each document. If Visio displays any repair, corruption, unreadable-content, macro, or compatibility prompt:

1. do not treat the case as passed;
2. capture the complete prompt in a screenshot;
3. cancel the prompt when possible;
4. retain the `.failed-*` evidence directory; and
5. report the case name and screenshot.

Do not approve a prompt merely to make the automation continue.

## Native operations performed per case

`scripts/validate_in_visio.ps1` performs these operations on a private copy of the generated VSDX:

1. open page one in Microsoft Visio through COM;
2. export `preview-before.png`;
3. locate two named connected shapes, including labels nested inside native groups;
4. move both shapes in X and Y through writable `PinX`/`PinY` cells;
5. verify the exact native connection signatures remain unchanged;
6. export `preview-after-move.png`;
7. save as `candidate-resaved.vsdx`;
8. close the document;
9. reopen the saved document read-only;
10. verify top-level shape and page connection counts remain stable;
11. verify moved coordinates and exact native connection signatures survive reopening;
12. export `preview-reopened.png`; and
13. write checksum-bound `acceptance-report.json` evidence.

The corpus uses these movement targets:

| Case | Moved shapes |
|---|---|
| Flowchart | `Order Valid?`, `Inventory Available?` |
| System architecture | `Edge Gateway`, `Stream Processor` |
| Contained schematic | `Processor`, `Radio` |

## Output contract

A successful corpus directory contains:

```text
corpus-report.json
flowchart/
  request.txt
  order-flow.vsdx
  generation-evidence/
  native-visio-acceptance/
system/
  request.txt
  iot-platform.vsdx
  generation-evidence/
  native-visio-acceptance/
contained/
  request.txt
  smart-camera.vsdx
  generation-evidence/
  native-visio-acceptance/
```

Each `generation-evidence` directory contains exact logical and transport prompts, exact raw provider responses, validated designs, layouts, initial/final VSDX files, Visio-exported previews, critique/revision evidence, hashes, provider/model identity, and source identity.

Each `native-visio-acceptance` directory contains:

- the exact candidate copied into the native test;
- the Visio-resaved candidate;
- before, moved, and reopened Visio PNG exports;
- `acceptance-report.json` with hashes for both VSDX files and all three PNGs, Visio version, shape counts, exact connection signatures, moved coordinates, and post-reopen checks.

## Manual visual review

Automation verifies reproducible lifecycle and connection-record behavior, but a person must inspect the three Visio previews and open documents for:

- source fidelity;
- readable labels and reference numerals;
- hierarchy and grouping;
- spacing and balance;
- connector crossings or obstruction;
- correct arrow direction;
- callout leader placement;
- native container behavior; and
- visible connector attachment while shapes move.

Record any visual defect against the exact VSDX SHA-256 and attach the relevant before/moved/reopened PNG. Do not regenerate and reuse an older acceptance report, because a regenerated VSDX is a new byte-level candidate.

## Acceptance decision

The scripts report `automation_passed_pending_manual_visual_review`; they never represent automation as final native/visual acceptance. H8–H10 close only when all three cases have:

- real provider design evidence;
- a Microsoft Visio-exported preview;
- real structured visual critique;
- at most one validated revision;
- successful native move/save/close/reopen reports;
- acceptable manual visual review; and
- checksum-bound evidence archived with the exact source revision.

Until the Windows output is returned and reviewed, these milestones remain **implemented and ready to execute, but not accepted**.
