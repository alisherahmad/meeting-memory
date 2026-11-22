# Evaluation

All commands run from the project root with `$env:PYTHONPATH = "src"`.

| What | Command | Needs key | Output |
|---|---|---|---|
| Re-verify and merge the gold set | `python -m meeting_memory.evaluate build-gold` | no | `gold_set.json` |
| Retrieval recall (BM25 / dense / hybrid) | `python -m meeting_memory.evaluate retrieval` | no | `results/retrieval_eval.json` |
| Agent on the 12 gold questions | `python -m meeting_memory.evaluate gold` | yes | `results/gold_eval_<time>.json` |
| The 25 Catalist questions + brief | `python -m meeting_memory answer-all` | yes | `answers.json`, `results/run_<time>/` |
| Grader emulation on answers.json | `python -m meeting_memory.evaluate check-answers -v` | no | stdout |
| Per-question record for the 25 | `python -m meeting_memory.evaluate cases --runs results/run_<time>/agent_runs.json` | no | `catalist_cases.json` |

## The two question sets
- **`gold_set.json`: 12 questions we wrote and checked by reading the transcripts.** Teams ES2005, ES2012, IS1000, IS1004, TS3005, TS3008, deliberately disjoint from the 25 Catalist questions so nothing hand-found leaks into the scored set. Each case has a reference answer, 2–4 key facts with accepted surface strings, and 2–3 evidence quotes from at least two meetings (all re-verified by code). `G-TS3008-2` is flagged ambiguous by its author (the final meeting never says outright that the docking station was dropped) and is reported separately.
- **`data/questions.json`: the 25 Catalist questions.** The answers are held back by Catalist, so we don't score correctness and don't reconstruct expected answers. We check what can be checked without them: verbatim citations, citation count, team scope, ≤3 sentences, meetings cited. `catalist_cases.json` records the result per question.

## Metrics and why these
| Metric | How | Why |
|---|---|---|
| Citation validity | ≥6 words, case/space-insensitive substring of one turn of the cited meeting | The grader checks exactly this; a failure is a guaranteed loss |
| Key-fact recall (gold) | Fraction of key facts whose accepted strings appear in the answer | Cheap and transparent; it over-matches loose strings and under-matches paraphrase, so it's paired with a human read |
| Cites a gold meeting | At least one citation comes from a meeting the gold evidence uses | Rough grounding check |
| Retrieval recall@k | Fraction of gold evidence turns inside the top-k chunks for the raw question | Separates "retrieval missed it" from "the model misread it" |
| Steps, tool calls, seconds, $ | From the agent trace and the `llm_calls` ledger | Cost and latency per answer; the 1,000-meeting projection |

LLM-as-judge is not used: the model would be grading itself.
