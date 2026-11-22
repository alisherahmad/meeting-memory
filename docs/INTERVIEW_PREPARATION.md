# Interview preparation

Everything here describes what the code actually does. If an answer isn't in the code, the honest answer is "I didn't build that, and here is how I would".

## Five-minute demo
1. **(30 s) Frame it.** "Meetings are a time series. The hard part isn't search, it's knowing what is *current*, and never citing words nobody said." Show the header: 138 meetings, 676,745 words, memory extracted.
2. **(60 s) Memory view → TS3012 → thread "speech recognition".** Click "state as of" **b**: the decision is "not implemented". Click **c**: reopened for the deluxe design. Click **latest**: dropped in d to meet the 12.50 budget. "The model labelled the relations. This status is computed by code from meeting order."
3. **(90 s) Ask view.** Pick a gold question (e.g. G-IS1000-2) or a new one the interviewer gives you. Narrate the live trace: list_meetings (roles per meeting: IS1000 swaps C/D), search_memory, search_transcripts, read_turns, submit_answer. If a quote is rejected, point at it: "code refused a quote that wasn't verbatim, and the agent fixed it".
4. **(30 s) Click a citation.** The transcript drawer opens at the exact turn with the quote highlighted.
5. **(60 s) Brief view → TS3012 → prepare for TS3012d.** "Built from a–c only; code picks the facts by status, the model writes sentences, code attaches the quotes."
6. **(30 s) Close on numbers:** 70/70 valid citations on the 25; 9/12 gold correct by human read; ≈ $8 per 1,000 meetings; whole build $1.49. Then one failure you understand (IS1000 role swap, "Right, Matthew?").

Fallback if the network or API fails: `python -m meeting_memory brief --team TS3012 --no-llm` (no model), the Memory view (no model), and `pytest -q` (no network).

## Architecture walkthrough (two minutes)
Raw layer (turns, chunks, FTS5, embeddings) → per-meeting extraction with prior team memory → validation by code (enums, earlier-only links, speakers, verbatim quotes, re-filing linked items) → items + threads → `compute_state` derives status → agent with 5 read-only tools + `submit_answer` gated by `verify_submission` → answers; `build_digest(as_of)` → brief. Files: `extraction.py`, `memory.py`, `agent.py`, `tools.py`, `quotes.py`.

## Twenty likely technical questions
1. **Why not put the transcripts in a long-context model?** The brief rules it out, and it doesn't scale: 880k tokens per question at 138 meetings, and impossible at 10k. My largest prompt is one meeting plus the team's compact memory.
2. **What exactly does the model decide?** What a meeting said (item kinds, statements, reasons, owners), how a new item relates to an earlier one, which tools to call, and the wording of answers and brief prose. Nothing else.
3. **What never touches a model?** Parsing, ordering, ids, chunking, search, citation verification, status over time, loop control, brief fact selection, scoring. See DECISION_LOG D1.
4. **How do you know what is current?** Meeting letter = clock. Relations from the extractor → `compute_state` (pure function). Forward links are rejected. `as_of` replays any point in time.
5. **How are back-references handled?** The extractor sees earlier memory with item ids, so "that idea from last time" can be linked to `TS3012b-014`. If it links but files the item in a new thread, code moves it into the linked item's thread.
6. **How do you guarantee citations pass?** `resolve_quote`: whole-token, case/space-insensitive match inside a single turn, or a conservative unique fuzzy repair; the emitted text is cut from the stored turn. ≥6 words. The agent can't finish without passing.
7. **Why hybrid retrieval?** It measured better: on 36 gold passages, recall@5 was BM25 36%, dense 33%, hybrid 44%.
8. **Why still have an agent if you have memory?** Memory is an index produced by a cheap model and can be wrong or incomplete; the agent verifies in the transcript and finds what extraction missed. A single retrieval pass finds under half the evidence.
9. **How do you stop the agent looping?** 14-step budget, 300 s wall clock, duplicate calls served from cache, a "submit now" warning at 2 steps left, a maximum of 2 rejected submissions, and terminal states.
10. **What happens when the API fails?** The SDK retries 429/5xx with backoff, then `LLMError`; the agent ends `failed`; ingest marks the meeting failed and blocks that team's later meetings; other teams continue. Re-runs resume.
11. **Why SQLite?** One file, transactional, FTS5 built in, zero ops. The swap path is Postgres + pgvector.
12. **Why Haiku?** Cost: about $1 for full-corpus extraction. I measured that low effort linked meetings poorly and medium was 3× better, so I chose medium; the agent runs at 1–2 cents per question.
13. **How do you handle speaker roles?** Per meeting: a regex on self-introductions first, then model claims that must quote that speaker's own turn, then a code-level check (`resolve_team_roles`): whoever directly addresses Matthew can't be Matthew, and the closest valid assignment wins. Letters swap between meetings (IS1000), so roles are never assumed team-wide. Be ready to tell the story of the first version being wrong in 9 of 11 meetings (people say their own names) and how reading every change caught it.
14. **Prompt injection?** Transcripts are data. Tools are read-only, with no write, network or file tools, so an injected instruction can't do anything. The UI renders text with `textContent`. A test fixture contains an injection line.
15. **How did you evaluate?** 12 hand-checked questions on 6 teams not in the 25; key-fact string matching + verbatim citation checks + reading the answers myself. Retrieval recall separately. Grader emulation on answers.json.
16. **Why not LLM-as-judge?** It grades the model with the model. I used transparent checks and a human read.
17. **What does ingesting 1,000 meetings cost?** Measured $0.0082/meeting on Haiku 5.5 (~15.5k in, ~13.8k out tokens), so ≈ $8.20 per 1,000 (≈ $4.10 with Batches), ≈ 3 h bounded by the output-token rate limit, plus ≈ 1 h CPU embeddings.
18. **How is state managed?** Persistent: SQLite. Derived on read: statuses. Per run: messages, tool cache, trace. No hidden memory between questions.
19. **How would you add a new meeting tomorrow?** Drop the file in and run `ingest`: unchanged meetings are skipped by hash, and only the new meeting is extracted, with its team's memory as context.
20. **What's tested?** 55 tests without network: parsing, quotes (incl. cross-turn rejection), time logic, extraction validation, ingest with a fake model, every agent terminal state, server validation.

## Ten difficult follow-ups
1. **"Your key-fact matching is gameable. Why trust it?"** It's a proxy; I report it next to a human read of every gold answer, and list where the strings over- or under-match.
2. **"Extraction is a single pass. What if it misses the decision?"** Then memory is incomplete, but the agent still searches raw transcripts. The cost shows up as more steps, and as wrong answers when retrieval also misses. Those cases are in the failure analysis.
3. **"What if the model mislabels a relation (confirms vs replaces)?"** Status will be wrong for that thread. I saw this in the pilot and reduced it with prompt rules plus a code rule (a decision that reopens a decision supersedes it). It isn't eliminated, which is why the agent verifies in the transcript.
4. **"Why should a strict verifier reject quotes the grader might accept?"** Asymmetric risk: an invalid citation definitely fails; a rejected-but-valid one only costs a retry.
5. **"Sequential extraction per team: doesn't that kill throughput?"** Parallelism is across teams (12 at once here). Within a team, order is the semantics. At 10k meetings across many teams, throughput is fine; very long single series would need windowed prior context.
6. **"Prior memory grows without bound."** It's capped at 60 threads × 6 items today; for long series I'd retrieve the relevant threads by the new meeting's content instead.
7. **"How would this break at 10k meetings?"** Dense brute force (needs ANN), SQLite single writer (Postgres), CPU embeddings (503 s for 5k chunks), and the prior-memory cap above. Lexical search and extraction scale linearly.
8. **"What if two speakers share a role or a letter is reused?"** The regex drops ambiguous roles; model claims must quote the speaker; conflicting roles in one meeting are dropped rather than guessed.
9. **"Why trust a cheap model?"** Its outputs are constrained (JSON schema), validated (links, speakers), and verified (quotes) by code; quality was measured on the pilot and the gold set. Switching to Opus is an env var.
10. **"What would you do with one more day?"** Re-extract with a stronger model on the teams where gold answers failed and compare; add a reranker if retrieval is the failure cause; build a review queue for unverified items.

## Failures and trade-offs (be ready to discuss)
- Three wrong answers and their root causes: EVALUATION_REPORT.
- Low vs medium effort on Haiku: cost vs linking quality (measured on TS3012).
- External-drive disconnect mid-run: no corruption thanks to per-meeting transactions and idempotent ingest.

## Decisions intentionally not made
No agent framework, no vector DB service, no reranker, no LLM judge, no auth/multi-tenancy, no cross-meeting identity resolution of people, no Batch API (it would be the production default for backfills).

## Study these files personally
| File / function | Why you must know it cold |
|---|---|
| `memory.compute_state` | The answer to "how do you know what is current" |
| `extraction.validate_extraction` | Every guarantee about extracted memory lives here |
| `quotes.resolve_quote`, `_exact_span`, `_fuzzy_span` | Why citations can't be invented |
| `agent.Agent.answer`, `_handle_submit` | The loop, the budgets, the terminal states |
| `tools.ToolBox.verify_submission` | The exit gate |
| `brief.build_digest`, `generate_brief` | No leakage; facts by code, prose by model |
| `retrieval.Retriever.search_chunks`, `_rrf` | Hybrid search and why it's scoped |
| `ingest._extract_team` | Ordering, cascade, refusal retry |
