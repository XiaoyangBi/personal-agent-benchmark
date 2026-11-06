# Personal Agent Benchmark

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Code: MIT](https://img.shields.io/badge/code-MIT-green)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-orange)](LICENSE-DATA)
[![Data: synthetic](https://img.shields.io/badge/data-synthetic-lightgrey)](#overview)

**English** · [简体中文](README.zh-CN.md)

> A synthetic, rule-scored benchmark for personal-assistant agents. Ten personas, 63 checkpoints each, four context conditions, deterministic offline scoring, and a reproducible five-model leaderboard.

**Contents:** [Overview](#overview) · [At a Glance](#at-a-glance) · [Dimensions](#dimensions) · [Evaluation Protocol](#evaluation-protocol) · [Dataset](#dataset) · [Repository Structure](#repository-structure) · [Quickstart](#quickstart) · [Leaderboard](#leaderboard) · [Reproducibility](#reproducibility) · [Scope and Limitations](#scope-and-limitations) · [Citation](#citation) · [License](#license)

---

## Overview

Personal Agent Benchmark tests whether an assistant can use a user's history correctly, keep a task moving, and refrain from acting without authorization. Each checkpoint supplies a trigger utterance, its evidence sessions, an environment state, and executable assertions. Scoring is deterministic and offline: fixed lexical, structural, and tool-call rules run against a structured reply, with no LLM judge.

The repository ships the full question bank, scoring rules, runner, saved model responses, and a single-round evaluation of five API models across all ten personas. A separate GPT runtime track provides a three-round stability snapshot on a different denominator; it is not part of the API leaderboard.

All personas, conversations, tool environments, canary strings, and results are synthetic. Nothing here corresponds to a real individual, real memory, or real business data.

## At a Glance

| Item | Value |
|---|---|
| Personas | 10 (synthetic, 23 sessions each) |
| Checkpoints per persona | 63 |
| Context conditions | C0, C1, C2, C3 |
| Items per full run, per model | 63 × 4 × 10 = 2,520 |
| Assertion rules | 1,540 across ten `assertions.json` files |
| Reply schema | `text`, `payload`, `citations`, `tool_calls` |
| Scoring | Deterministic, offline, no LLM judge |
| Runtime dependencies | Python standard library only |

## Dimensions

| Code | Dimension | What it tests |
|---|---|---|
| D1 | Memory | Writing, updating, recalling, and proactively using user facts |
| D2 | Task progression | Goal reconstruction, obstruction handling, interruptibility, sensible abandonment |
| D3 | Restraint | Overreach, excessive confirmation, interruption, sycophancy |
| D4 | Writing | Ghostwriting for the user, internal summaries, writing assistance |
| D5 | Rich UI | Validity, clarity, behavior, and restraint of cards and buttons |
| D6 | Longitudinal consistency | Preference drift, relationship continuity, memory confidence across months |
| D7 | Environment experience | Tool and environment state usage, boundaries, and failure handling |

A checkpoint may belong to several dimensions; the `dim` field in `data/persona-XX.json` records composite labels such as `D1/D3`. Full definitions are in [docs/specification.md](docs/specification.md).

## Evaluation Protocol

Every checkpoint runs once under each condition. The gap between conditions separates retrieval failures from reasoning failures.

| Condition | Input | Purpose |
|---|---|---|
| C0 | Current session only | No-memory lower bound; detects checkpoints that do not require memory |
| C1 | Current session + designated evidence session | Oracle condition; removes retrieval as a variable |
| C2 | All history up to the current turn, under an 8,000-token character-estimate budget | Full-context control; truncation is recorded in result metadata |
| C3 | Current session + top-3 naive retrieved memories | Tests memory retrieval and evidence reading |

Construction, retrieval, and budgeting are implemented in `persona-01-linzhou/runner/conditions.py` and `memory.py`; the protocol document is [docs/protocol.md](docs/protocol.md). Tools are simulated: no real order, message, or file operation is executed.

A checkpoint passes when all of its rules pass. These rules are lexical, structural, and tool-parameter checks, so they are a weak proxy for semantic quality. See [Limitations](#scope-and-limitations).

## Dataset

| Path | Contents |
|---|---|
| `persona-XX-*/profile.md` | Synthetic persona profile |
| `persona-XX-*/data/persona-XX.json` | Checkpoints, planted facts, distractors, targets, canary |
| `persona-XX-*/data/sessions.json` | 23 sessions of user utterances |
| `persona-XX-*/data/assertions.json` | Per-checkpoint scoring rules used for the leaderboard |
| `persona-XX-*/data/dry_run_replies.json` | Reference fixtures used to verify the rules themselves |
| `persona-XX-*/results/dry-run.json` | Four-condition fixture pipeline check; **not** a model score |
| `persona-XX-*/results/api-v2-nothink-<model>.json` | Formal single-round model results |

`persona-01-linzhou` additionally carries `data/assertions-v3.json` (108 rules) and frozen GPT-runtime inputs and replies. That scoring scale has a different denominator and must not be merged with the API leaderboard. The 63-checkpoint index is [docs/checkpoint-index.md](docs/checkpoint-index.md); persona construction and validation reports are [docs/personas.md](docs/personas.md) and [docs/persona-validation.json](docs/persona-validation.json).

## Repository Structure

```
personal-agent-benchmark/
├── README.md                      # this file (English)
├── README.zh-CN.md                # Simplified Chinese
├── LICENSE                        # MIT, code
├── LICENSE-DATA                   # CC BY 4.0, data and evaluation materials
├── docs/
│   ├── specification.md           # dimensions, scoring, data schema (Chinese)
│   ├── protocol.md                # four-condition protocol (Chinese)
│   ├── checkpoint-index.md        # 63-checkpoint index
│   ├── personas.md                # persona navigation
│   ├── api-v2-nothink-ranking.md/json      # leaderboard
│   ├── api-v2-nothink-validation.json     # integrity and recomputation report
│   ├── api-v2-nothink-sensitivity.json    # four-denominator sensitivity
│   ├── model-results.md/json      # historical persona-01 experiment index
│   ├── run-inventory.json         # every result file with source SHA-256
│   └── trace-availability.json    # what trace material exists and what does not
├── persona-01-linzhou/            # original persona; also hosts the shared runner
│   ├── runner/                    # conditions, assertions, execution, replay
│   ├── data/                      # question bank and scoring rules
│   └── results/                   # saved responses, attempts, suites, pilot archive
├── persona-02-xutang/ … persona-10-guyao/
└── tools/
    ├── evaluation/                # suite runner, ranking, sensitivity, validation
    ├── personas/                  # persona generation and bundle validation
    └── publication/               # release indexes and integrity checks
```

## Quickstart

Everything needed to reproduce the published numbers is already in the repository. No API key, no network access, and no third-party package are required.

```bash
git clone https://github.com/XiaoyangBi/personal-agent-benchmark.git
cd personal-agent-benchmark

# Recompute the leaderboard and verify integrity from saved responses
python3 tools/evaluation/validate_api_suite.py
python3 tools/evaluation/rank_api_suite.py --allow-partial
python3 tools/evaluation/sensitivity_api_suite.py

# Validate the question bank and the release snapshot
python3 tools/personas/validate_bundle.py --require-dry-run
python3 tools/publication/validate_release.py
```

To evaluate your own system, see `tools/evaluation/run_api_suite.py --help`. It requires your own model credentials and writes results alongside the published ones. Keep credentials out of the repository. To verify the scoring pipeline without a model, run the runner in dry-run mode as described in [persona-01-linzhou/runner/README.md](persona-01-linzhou/runner/README.md).

## Leaderboard

Single round, five API models, all ten personas. Ranking uses the 2,488 items with a valid reply from every model; 32 items without a common valid reply are excluded. Metric: pooled pass rate under each persona's `assertions.json`.

| Rank | Model | Passed | Pass rate |
|---:|---|---:|---:|
| 1 | hy4-preview | 1,311 / 2,488 | 52.69% |
| 2 | deepseek-v4-flash | 1,237 / 2,488 | 49.72% |
| 3 | glm-5.3-flash | 1,234 / 2,488 | 49.60% |
| 4 | mimo-v2.6-flash | 1,199 / 2,488 | 48.19% |
| 5 | minimax-m3.1-flash | 1,122 / 2,488 | 45.10% |

Full report: [docs/api-v2-nothink-ranking.md](docs/api-v2-nothink-ranking.md). This is a task-performance comparison under controlled decoding settings, not a general model-capability ranking and not a significance test.

## Reproducibility

- **Valid replies only.** A reply must have `text` as a string, `payload`/`citations`/`tool_calls` as lists, no `error`, and a non-null `score.passed`. Transport errors, empty responses, missing structured fields, and wholly missing checkpoints are technical failures: they are not scored as zero and do not enter the common denominator.
- **First-valid retention.** Later attempts only fill missing or technically invalid keys. An existing valid reply is never replaced because another attempt scored higher.
- **Four-denominator sensitivity.** The rank order is identical under the common-valid denominator, the full 2,520-item denominator with invalid items scored as zero, each model's own valid denominator, and a normalized recovery of recoverable replies. See [docs/api-v2-nothink-sensitivity.json](docs/api-v2-nothink-sensitivity.json).
- **Decoding.** DeepSeek, GLM, Hy4, and MiMo use non-thinking output. MiniMax uses standard output because the gateway returns an unparsable payload when thinking is disabled. Decoding mode is validated per model but remains a confound.
- **Separate tracks.** GPT runs in the WorkBuddy runtime as an independent descriptive track and is excluded from the API leaderboard. No cross-environment significance claim is made.
- **Archived runs.** Deprecated pilots, rate-limited trials, and standard-mode first runs live in `persona-*/results/pilot/` and are excluded from the leaderboard. `dry-run.json` is a fixture check.
- **Trace boundary.** Structured contexts, replies, and tool calls are saved; full low-level execution logs, live read evidence, and real tool side effects are not. See [docs/trace-availability.json](docs/trace-availability.json).

The three evaluation scripts read saved results only and never call a model. `validate_api_suite.py` independently recomputes scores and cross-checks invalid-item classification, first-valid retention, and the published ranking.

## Scope and Limitations

- All ten personas share 63 scenario types to keep coverage comparable. They are an expanded question set, not ten independent samples; significance cannot be derived from them.
- Fixed assertions are a weak proxy for semantic quality, sycophancy, and writing style. Historical rule corrections are recorded in the result metadata.
- The leaderboard is a **single round** with no repeated sampling. Bootstrap ranges over synthetic personas measure persona sensitivity, not model significance.
- Early 58-item and 63-item variants, different assertion versions, retry-merged runs, pilot tracks, and runtime versus API tracks are kept separate. Always check the denominator and scoring scale before comparing.
- The complete underlying execution trace for the GPT runtime was not obtained; structured inputs and outputs are not presented as full traces.
- The public snapshot is current as of 2026-11-04. It is an observation under a specific question bank and decoding configuration, not a validated general capability benchmark.

## Citation

```bibtex
@misc{personal_agent_benchmark_2026,
  title  = {Personal Agent Benchmark: A Synthetic Rule-Scored Evaluation Suite},
  author = {XiaoyangBi},
  year   = {2026},
  url    = {https://github.com/XiaoyangBi/personal-agent-benchmark}
}
```

Related work: [LongMemEval](https://arxiv.org/abs/2410.10813) (ICLR 2025) for oracle-style evidence design; the four-condition protocol follows that line of work.

## License

- **Code** (`tools/`, `runner/`, scripts): [MIT](LICENSE).
- **Data and evaluation materials** (`persona-*/data/`, `persona-*/results/`, `docs/`, `profile.md`, reports): [CC BY 4.0](LICENSE-DATA).

Attribution is required for the data. All data is synthetic and carries no personal information. See [LICENSE-DATA](LICENSE-DATA) for the exact scope.
