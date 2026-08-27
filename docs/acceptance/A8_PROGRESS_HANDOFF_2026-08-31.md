# A8 PDF/DOCX Analysis Handoff for 2026-08-31

**Written:** 2026-08-27T16:46:28+05:00

**Scope:** PDF/DOCX image-to-text analysis only. VSDX generation and Visio acceptance
are out of scope.

## Safe stopping state

- The last validated implementation revision is
  `d49feaf03ea5a1c7df874b9739c96153a7483258`. This handoff is committed after that
  revision, so the report's `source_revision` on resume must equal the then-current
  clean `HEAD`; it need not equal `d49feaf`.
- The full seven-case run was started and deliberately interrupted at the end of the
  work day before any case completed. The atomic runner published no
  `a8-full-d49feaf` output, its temporary staging directory was cleaned up, and no
  corpus or provider process remains active.
- The intended full-run output path is therefore unused and safe to use on resume:
  `/home/murtaza/Murtaza/Visiogen/acceptance/a8-full-d49feaf`.
- The latest full local test suite passed: `516 passed in 45.65s`.

## Granular commits completed and pushed

- `ba5e88e` — omit ungrounded diagram annotations with an audit limitation;
- `6942742` — classify provider timeouts as explicit transient errors and retain safe
  attempt metadata;
- `a0fc5fe` — retry transient analysis timeouts within existing bounded call budgets,
  preserve timeout traces, and publish timeout error sidecars;
- `d49feaf` — re-ground exact object labels to matching observation evidence, accept
  attached Unicode numeric runs such as `SP₆`, and omit still-unsupported object text
  only on the final bounded attempt.

Earlier supporting A8 commits already on `main` are `64df56b`, `7a781b3`,
`2b3c842`, and `967899b`.

## Passing authenticated evidence

### NIST vector PDF — complete on the current revision

- Report:
  `/home/murtaza/Murtaza/Visiogen/acceptance/a8-object-rerun-d49feaf/execution-report.json`
- Source revision: `d49feaf03ea5a1c7df874b9739c96153a7483258`
- Result: 3/3 candidates complete, zero failures, 20 total calls including
  classification.
- Bundle SHA-256:
  `f04ed7d2e8602983b538c57278704318683c56160021d91e2f1315e63099de3b`.
- Candidate calls: 5, 6, and 8.
- Candidate 3 exercised the real timeout retry: observation attempt 1 timed out after
  approximately 300.1 seconds, the retry succeeded, and the candidate stayed within
  its four-call semantic budget (2 observation plus 2 reconstruction calls).
- Preserved timeout sidecar:
  `/home/murtaza/Murtaza/Visiogen/acceptance/a8-object-rerun-d49feaf/cases/held-vector-pdf/bundle/candidate-0003/traces/observation-01-error.json`.

### NASA low-quality scan — complete on the preceding timeout revision

- Report:
  `/home/murtaza/Murtaza/Visiogen/acceptance/a8-timeout-rerun-a0fc5fe/execution-report.json`
- Source revision: `a0fc5fefe3cca40a49312a5cba56238374dfe337`
- Result: 1/1 candidate complete, zero failures, 5 total calls including
  classification.
- Bundle SHA-256:
  `0b163d11df8954a7b7cea0712e44d91d30c5856458431eaab49d1e9c57b9da72`.
- This execution did not time out; the full seven-case run must revalidate NASA and
  NIST together on one clean, unchanged revision.

## Monday resume sequence

1. Verify the exact clean revision:

   ```bash
   cd /home/murtaza/Murtaza/Visiogen/project
   git status --short --branch
   git rev-parse HEAD
   ```

   Expected: `main...origin/main` and no changed files. Record the returned `HEAD` and
   keep it unchanged through the full corpus and hardening runs.

2. Run the full immutable seven-case corpus. Keep the task open and report progress at
   least every few minutes with the current case, candidate count, call count when
   visible, elapsed time, and realistic ETA.

   ```bash
   UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
     scripts/run_analysis_release_corpus.py \
     --corpus /home/murtaza/Murtaza/Visiogen/acceptance/a8-corpus/corpus.json \
     --output /home/murtaza/Murtaza/Visiogen/acceptance/a8-full-d49feaf \
     --model gpt-5.6-sol \
     --timeout 300
   ```

   This must finish with `status: passed`, `complete_corpus: true`, seven complete
   cases, `source_clean: true`, and `source_revision` equal to the `HEAD` recorded in
   step 1. Do not tune against held-out outputs during this release run. The `d49feaf`
   suffix in the output path is a lineage label; the report metadata is authoritative.

3. If and only if the full corpus passes, run deterministic hardening from the same
   unchanged revision:

   ```bash
   UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
     scripts/run_analysis_hardening_acceptance.py \
     --output /home/murtaza/Murtaza/Visiogen/acceptance/a8-hardening-d49feaf
   ```

4. If execution and hardening both pass on the same revision, generate the blinded
   review packet. Do not invent reviewer identities or judgments:

   ```bash
   UV_CACHE_DIR=/tmp/visiogen-progress-uv-cache uv run python \
     scripts/prepare_analysis_release_reviews.py \
     --corpus /home/murtaza/Murtaza/Visiogen/acceptance/a8-corpus/corpus.json \
     --execution /home/murtaza/Murtaza/Visiogen/acceptance/a8-full-d49feaf/execution-report.json \
     --output /home/murtaza/Murtaza/Visiogen/acceptance/a8-reviews-d49feaf.json
   ```

5. Two independent human reviewers must complete the distinct diagram and consistency
   passes. Only then run `scripts/evaluate_analysis_release.py` against the exact
   execution bundle hashes and hardening report.

## Remaining release gates

- Full seven-case authenticated execution from one clean revision;
- deterministic hardening from that same revision;
- checksum-bound blinded packet;
- two independent completed human review passes;
- final release scoring and acceptance decision.

No code defect is currently known from the targeted NIST and NASA evidence. The next
unknown is full-corpus stochastic behavior under the single current revision.
