# Evaluation report

_All numbers are measured on 2026-11-22 with Claude Haiku 5.5 (extraction at effort `medium`, agent and brief at `medium`), local MiniLM embeddings, and SQLite FTS5. Raw outputs are in `evaluation/results/`._

## 1. Headline results
| What | Result | Source |
|---|---|---|
| Meetings ingested | 138/138 (676,745 words, 48,148 turns, 5,052 chunks) | `ingest_report_pass1.json`, `_pass2.json` |
| Memory extracted | 3,379 items in 1,293 threads; **98.9% verifiable** (3,341 items have ≥1 quote verified against the transcript) | DB |
| Extraction quotes | 3,388 proposed by the model → 3,305 exact, 41 repaired by code, 42 rejected (98.8% usable) | ingest reports |
| **Catalist 25: citations** | **70/70 verbatim-valid** (grader-equivalent check), every answer 1–3 citations, ≤3 sentences, 23/25 cite ≥2 meetings | `check-answers`, `catalist_cases.json` |
| Catalist 25: completion | 25/25 `answered`; mean 4.0 model steps, 4.2 tool calls; median 10 s; $0.041 for all 25 | `run_20261122_160536` |
| TS3012 brief | 4 sections, 34/34 citations valid, built from meetings a–c only | `answers.json`, `brief.json` |
| **Gold set (12, hand-checked)** | **Human read: 9 correct, 2 mostly correct, 1 wrong.** Key-fact proxy 0.875 (0.955 excluding the ambiguous case); 100% citations valid; 100% cite a gold meeting | `gold_eval_20261122_160739.json` |
| Retrieval (single query = raw question) | gold-evidence recall@5: BM25 0.36, dense 0.33, **hybrid 0.44**; @20: 0.64 / 0.61 / **0.72** | `retrieval_eval.json` |
| Tests | 55 passing, no network, ~10 s | `pytest` |
| Total API spend, entire build | **$1.49** (pilots, two extraction passes, three answer runs, three gold runs, briefs) | `llm_calls` ledger |

**What we can't measure:** correctness on the 25 Catalist questions. Catalist holds the answers back, and we didn't hand-derive them. The gold set is our proxy.

## 2. Gold set: per question
Key facts are matched by surface strings (a cheap proxy); the **human verdict** is from reading each answer against the transcript.

| Case | Category | Key facts | Human verdict | Note |
|---|---|---|---|---|
| G-ES2005-1 | number | 4/4 | correct | 14.60 → 11.60 EUR, double-curve item removed |
| G-ES2005-2 | decision change | 4/4 | correct | regular batteries → rechargeable + stand; dynamo/solar rejected with reasons |
| G-ES2012-1 | decision change | 3/4 | correct | The "missing" fact (12.5 total) wasn't asked by the question |
| G-ES2012-2 | attribution | 4/4 | correct | |
| G-IS1000-1 | commitment | 4/4 | **wrong speaker roles** (content correct) | Labels C as UI and D as ID in meeting d; in IS1000d it is the other way round. See failure 2 |
| G-IS1000-2 | attribution | 4/4 | correct | Correctly calls the ID "Speaker D" in meeting c |
| G-IS1004-1 | decision change | 3/3 | correct | |
| G-IS1004-2 | number | 4/4 | correct | |
| G-TS3005-1 | decision change | 3/4 | **mostly correct** | Status before the final meeting given as "optional / chip in test phase" (true, in TS3005c), but it misses that the PM called it the remote's "unique idea". See failure 3 |
| G-TS3005-2 | attribution | 4/4 | correct | |
| G-TS3008-1 | attribution | 4/4 | mostly correct | Core correct; adds a loosely supported remark about Speaker B |
| G-TS3008-2 | decision change (ambiguous) | 0/4 | **wrong** | Credits the PM with proposing the base; it was Speaker D. See failure 1 |

Counting the IS1000-1 role error as a failure, the human score is **9 fully correct of 12**. In an earlier run, an answer named ES2005's Industrial Designer "Arlo", a name the transcript doesn't establish. That kind of run-to-run variance is why the answer prompt now forbids details the question didn't ask for.

## 3. Three questions the agent got wrong, and why
**1. G-TS3008-2: "Who proposed the base/docking station?"** The agent credits Speaker A (Project Manager); the transcript has Speaker D (Marketing Expert) at 00:27:49: *"in the base we could like make uh a button, and if you push it, the remote control itself s makes noise"*. A only adds recharging afterwards (00:28:29).
*Root cause:* **extraction conflation**. Memory item `TS3008b-033` ("the remote stands upright in a base unit"), credited to A, was built from A's earlier remark that the remote should stand up "like a vase". That's a shape idea, not the base. The agent took the memory item over the transcript order. The correct item (`TS3008b-035`, D's beep button) was also in memory.
*Fix direction:* when a question asks "who first proposed X", have the agent read the turns around every candidate item and decide by timestamp in code. Add an extraction rule that a proposal's speaker must be the one who introduces the concept.

**2. G-IS1000-1: speaker roles in meeting d.** In IS1000d the letters swap: Speaker C says *"Right, Matthew?"* and Speaker D asks *"What do you say, Mael?"*, so C is Mael (Industrial Designer) and D is Matthew (UI Designer). The system resolved the opposite, so the answer's numbers are right but its people are wrong.
*Root cause:* role resolution for meetings without self-introductions is the model's job. The extractor is shown earlier meetings' roles as a hint and carried the old mapping forward. Code only checks that a role's evidence quote comes from that speaker's own turn, not that it *supports* the role. The quote used for C = UI was C presenting the costs, which is actually the Industrial Designer's task.
*Fix direction:* deterministic vocative detection ("Right, Matthew?" means this speaker is not Matthew; "What do you say, Mael?" means not Mael) as a code-level constraint on roles; stop passing earlier mappings as a hint, and pass the names only.

**3. G-TS3005-1: "What was speech recognition's status before the final meeting?"** The agent says it was an optional extra whose chip was "still in a test phase". That is true, and quoted from TS3005c. But it misses the PM calling speech control *"the unique uh idea of our remote"* in the same meeting, the more important part of its status.
*Root cause:* **retrieval and selection**. The agent found one supporting passage per meeting and stopped; it didn't look for a second, more central statement. With 4 model steps on average, the agent is efficient but not exhaustive.
*Fix direction:* for "status before X" questions, read the whole thread (`get_thread`) and the turns around each item, not just the first hit.

## 4. Failures found and fixed during the build (system, not answers)
| Problem | How found | Fix | Verified by |
|---|---|---|---|
| Low-effort Haiku barely linked meetings (1 superseded decision on TS3012) | TS3012 pilot, read by hand | Effort `medium` (3× more cross-meeting links), prompt rules on threads and "confirms" | `linkstats.py` comparison; Memory view |
| Linked items opened new threads instead of joining the linked one | Pilot 2 | **Code** re-files any item with a relation into its target's thread (203 items moved in the full run) | `test_linked_item_is_refiled_into_target_thread` |
| A decision that "reopens" an earlier decision left both current | Pilot 1 | Code rule: reopened by a *decision* means superseded | `test_reopen_by_decision_supersedes...` |
| Rate limits at 12-way concurrency (5 meetings failed, 8 blocked) | Full ingest | Ingest backoff 30/60/120 s on retryable errors; resume pass at concurrency 4 | `test_retryable_error_backs_off_then_succeeds`; pass 2: 13/13, 0 failures |
| Q04 exhausted all 14 steps re-sending an invalid `submit_answer` | Catalist run 2 | Error now names the missing field; truncated (`max_tokens`) tool calls are never executed; `submit_answer` is `strict` | `test_truncated_tool_call_is_not_executed`, `test_invalid_submission_names_the_missing_field` |
| Strict schema rejected `maxItems` (API 400) | Single-question test before a full run | Bounds removed from the tool schema; still enforced by pydantic | Q04 re-run |
| Answers mentioned system internals ("the memory index…"), ran long, cited only the final meeting | Reading all 25 answers | Prompt rules + one round of code-enforced format feedback; the 3-sentence limit is hard (third time: code keeps the first 3 sentences) | 2+ meetings cited: 15/25 → 23/25; over-length: 1 → 0; `test_sentence_limit...` |
| External SSD disconnected mid-run | Shell lost the working directory | None needed: per-meeting transactions + idempotent ingest; DB `integrity_check` ok | Resume run |

## 5. Retrieval
Raw question text as a single query, team-scoped, over 36 gold evidence passages:

| k | BM25 | Dense (MiniLM) | Hybrid (RRF) |
|---|---|---|---|
| 5 | 0.36 | 0.33 | **0.44** |
| 10 | 0.53 | 0.44 | **0.56** |
| 20 | 0.64 | 0.61 | **0.72** |

Hybrid beats either side at every k, but one query still misses about half the evidence. This is the quantitative reason for (a) an agent that issues several targeted queries and reads around hits, and (b) a memory layer whose items are written in normalised language. Small sample (12 questions), so differences of a few points are noise.

## 6. Cost and time, and what 1,000 meetings would take
Measured on 134 meetings in the final extraction passes (Haiku 5.5, effort `medium`):

| Per meeting | Value |
|---|---|
| Input tokens | ~15.5k (one meeting ≈ 6.4k transcript tokens on average + numbered-turn overhead + prior team memory + system prompt) |
| Output tokens | ~13.8k (mostly adaptive thinking; the JSON itself is ~3–5k) |
| Cost | **$0.0082** |
| Latency of one call | 70–100 s |

**1,000 meetings:**
| Stage | Cost | Time |
|---|---|---|
| Parse + index (code) | $0 | ~1 min |
| Extraction (Haiku 5.5, standard API) | **≈ $8.20** | **≈ 3 h** at the ~10 s/meeting throughput we sustained with 12 parallel teams. Throughput is bounded by the account's output-token rate limit, not by per-team ordering: 1,000 meetings ≈ 250 independent teams |
| Extraction via Message Batches API | ≈ $4.10 (50% price) | asynchronous, typically < 24 h |
| Chunk embeddings (local CPU MiniLM) | $0 | ≈ 1 h on this laptop CPU (503 s per 5,052 chunks); minutes on a GPU |
| Item embeddings | $0 | ≈ 15 min CPU |
| **Total** | **≈ $8 (≈ $4 batched)** | **≈ 3–4 h** |

For comparison, **not measured**: the same token profile on Claude Opus 5.5 would be about $0.34/meeting (≈ $340 per 1,000). On our 12 gold questions, measured quality with Haiku is already 9–11/12, so the 40× price isn't justified for bulk extraction without evidence that it fixes the remaining failure types. Failures 1 and 2 are design gaps that code can fix.

**Answering:** $0.0016 per question, median 10 s (Haiku, ~4 steps). At 1,000 questions a day that's about $1.60.

## 7. What the evaluation does not show
- Correctness on Catalist's 25 (held back).
- Statistical confidence: 12 gold questions is a smoke test, not a benchmark.
- Answer stability: the agent is non-deterministic. Across three gold runs the verdicts were stable, with two exceptions: one run named ES2005's Industrial Designer "Arlo" (not established by the transcript), and the IS1000 meeting-d role swap appeared in **every run whose answer named roles in meeting d** (runs 2 and 3). It is systematic, not noise, because the wrong roles are stored in memory.
- The key-fact proxy both over-matches (generic strings such as "kept", "16") and under-matches (paraphrase), so it's reported only next to the human read.
