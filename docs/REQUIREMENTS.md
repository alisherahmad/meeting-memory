# Requirements traceability

P0 = explicitly mandatory · P1 = important to a successful delivery · P2 = optional · P3 = experimental.
Status is filled from evidence, not from "the code exists". See EXECUTION_STATUS.md for the latest run.

| ID | Pri | Source | Requirement | Acceptance criteria | Implementation | Verification | Status |
|---|---|---|---|---|---|---|---|
| R1 | P0 | S3 | Ingest all meetings into a searchable store | 138/138 parsed, word count matches brief, searchable by team | `transcripts.py`, `store.py`, `chunking.py`, `ingest.py stage_parse` | `ingest --no-extract` report; `test_pipeline.py` | Done (676,745 words, 48,148 turns, 5,052 chunks) |
| R2 | P0 | S2 | No whole-corpus prompts; scales to 10k meetings | Max prompt = one meeting + team memory; search is index-backed and scoped | `extraction.py` (one meeting per call), `retrieval.py`, `tools.py` | Code review; token ledger; scale section | Done by design; ledger numbers in EVALUATION_REPORT |
| R3 | P0 | S4/Q2 | Answer each of the 25 questions in 1–3 sentences | 25 answers in `answers.json`; ≤3 sentences | `agent.py`, `cli.py answer-all` | `evaluate.py check-answers` | Blocked until an API key is set |
| R4 | P0 | S4/Q4 | 1–3 citations per answer, ≥6 words, verbatim, one turn | 100% of emitted citations pass the grader-equivalent check | `tools.verify_submission`, `quotes.resolve_quote`, `SubmitAnswerArgs` | `test_agent.py`, `test_transcripts_quotes.py`, `check-answers` | Logic verified by tests; full run blocked on key |
| R5 | P0 | S5/Q5 | TS3012 brief: decided / changed / open actions + owners / open disagreements, every point cited | 4 sections; each point has ≥1 verified citation; no content from TS3012d | `brief.py` | `test_pipeline.py::test_ingest_builds_time_aware_memory` (no-leak + verbatim), `check-answers` brief check | Logic verified; real brief blocked on key |
| R6 | P0 | S6 | Output JSON schema | Exact keys `answers[].question_id/answer/citations[].meeting_id/quote`, `brief` | `cli.py cmd_answer_all` | Inspect file; `check-answers` parses it | Implemented |
| R7 | P0 | S7 | Real agent behaviour: retrieve, loop, steps | Multi-step tool loop with ≥2 retrieval tools; traces recorded | `agent.py`, `tools.py` | Traces in `evaluation/results/*/agent_runs.json`; UI trace | Implemented; tested with fake model |
| R8 | P0 | S8 | Memory over time: know what is current | Superseded vs current computed; "as of" replay; back-references linked | `memory.py`, `extraction.py` (prior memory in prompt), UI Memory view | `test_memory_state.py` (8 tests); gold `decision_change` cases | Logic verified; real data blocked on key |
| R9 | P0 | S9 | Model-vs-code boundary stated and defended | Table of every step with owner (model/code) and why | DECISION_LOG.md, WRITEUP.md | Review | Done |
| R10 | P0 | S10 | ≥10 own questions with checked answers, scored | ≥10 cases, verified evidence quotes, a score per case | `evaluation/gold_set.json` (12), `evaluate.py gold` | `build-gold` re-verifies 36/36 quotes | Gold set done; scoring blocked on key |
| R11 | P0 | S11 | Cost and time to ingest 1,000 meetings | Extrapolated from measured tokens/latency, with assumptions | `llm_calls` ledger, `cli stats` | EVALUATION_REPORT | Blocked on key (needs a measured run) |
| R12 | P0 | S12 | Three wrong answers explained | ≥3 failures with root cause | EVALUATION_REPORT | Review | Blocked on key |
| R13 | P0 | S13 | Platform reasoning: framework, models, APIs, where they broke | Written, with observed breakages | WRITEUP, DECISION_LOG | Review | Partly (observed: torch import time; letter swaps) |
| R14 | P0 | S14 | README with run instructions; one-page write-up | Fresh clone can run tests, ingest, ask | README.md, docs/WRITEUP.md | Follow README | In progress |
| R15 | P0 | Q3 | Speaker letter + role | Roles resolved per meeting with evidence | `roles.py`, extraction roles, `list_meetings` tool | `test_pipeline.py::test_regex_roles`, extraction validation test | Implemented |
| R16 | P1 | S14 | Take new questions live | CLI `ask` and web UI; no question-specific code | `cli.py ask`, `server.py`, UI | Manual demo | Implemented; needs key |
| R17 | P1 | — | Failure handling: provider errors, bad output, loops | Terminal states; step/time budgets; dedup; invalid args → tool error | `agent.py`, `llm.py`, `ingest.py` | `test_agent.py` (10 tests), ingest failure test | Done |
| R18 | P1 | — | Prompt-injection resistance | Transcript text cannot widen permissions; tools read-only | `tools.py` (no write tools), system prompts, `textContent` in UI | `test_tool_surface_is_read_only`, fixture contains an injection line | Done (by construction) |
| R19 | P1 | — | Idempotent, incremental ingest | Unchanged meetings skipped; changing meeting k re-extracts k.. | `ingest._extract_team`, content hash | `test_ingest_builds_time_aware_memory` (re-run is a no-op) | Done |
| R20 | P1 | — | Retrieval quality measured | Recall on gold evidence for BM25 / dense / hybrid | `evaluate.py retrieval` | `evaluation/results/retrieval_eval.json` | BM25 done; dense/hybrid running |
| R21 | P2 | — | Web UI: ask with live trace, memory timeline, brief | Works at desktop and mobile widths, no console errors | `server.py`, `static/` | Browser inspection | Implemented; empty states inspected |
| R22 | P2 | — | Deterministic brief when the model is down | Brief renders from memory without an LLM | `brief.generate_brief(use_llm=False)` | `test_brief_falls_back_without_model` | Done |
| R23 | P3 | — | Batch API for 50% cheaper bulk ingest | — | Not built | — | Will not do (documented as production step) |
