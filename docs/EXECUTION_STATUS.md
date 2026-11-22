# Execution status

_Last updated: 2026-11-22. Deadline: 2026-11-23._

## Current phase
**Stage D → F blocked on one external input: an Anthropic API key.** Everything that doesn't call the model is built, tested and inspected. Memory extraction, the 25 answers, the gold-set score, the TS3012 brief and the measured cost all need the key.

## Completed milestones
- [x] Reconnaissance: PDF (2 pages), zip listed then extracted, `questions.json`, credits; inventory in SOURCE_LEDGER
- [x] Requirements, question analysis, product spec, architecture, decision log, data flow
- [x] Parse + index all 138 meetings: 676,745 words, 48,148 turns, 5,052 chunks in ~9 s, no model
- [x] Memory model (relations → status in code) with `as_of` replay
- [x] Per-meeting extraction with prior memory as context + code validation and quote verification
- [x] Bounded agent loop with verified `submit_answer`, terminal states, dedup, budgets
- [x] Brief generator (model prose over a code-selected digest; deterministic fallback)
- [x] Gold set: 12 questions on 6 teams disjoint from the 25; 36/36 evidence quotes re-verified by code
- [x] Chunk embeddings: 5,052 chunks in 503 s on CPU (MiniLM, local)
- [x] Retrieval eval (`evaluation/results/retrieval_eval.json`), gold evidence recall, single query = raw question: k=5 BM25 0.36 / dense 0.33 / hybrid 0.44; k=20 BM25 0.64 / dense 0.61 / hybrid 0.72
- [x] 43 automated tests passing (no network)
- [x] Web UI running; empty states inspected at desktop width
- [x] Git checkpoints

## Remaining mandatory work (in order, once a key is set)
1. `python -m meeting_memory ingest --report evaluation/results/ingest_report.json` (full extraction; measures cost/time)
2. `python -m meeting_memory.evaluate gold` (score, find failures, fix, rerun)
3. `python -m meeting_memory answer-all` → `answers.json` + TS3012 brief; `evaluate check-answers`
4. Fill EVALUATION_REPORT (measured numbers, 3 failures), WRITEUP cost section, FINAL_REVIEW
5. UI inspection with real memory (desktop + mobile)

## Blockers
| Blocker | Impact | Smallest decision needed |
|---|---|---|
| No `ANTHROPIC_API_KEY` on this machine (no `ant` profile either) | All model-dependent P0 items | Add the key to `.env` |

## Failed tests
None (43/43).

## Decisions requiring attention
- Model for extraction: default `claude-opus-5-5`. Estimated full-corpus extraction cost is ~$10–15 (rough pre-run estimate, replaced by measured numbers after the run). `claude-haiku-5-5` would be ~40× cheaper per token but untested here.

## Next three actions
1. Full ingest with extraction
2. Gold-set evaluation and failure analysis
3. Generate `answers.json` and the brief
