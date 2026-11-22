# Meeting Memory: one-page write-up

**Architecture.** One SQLite file, two layers. The *raw layer* keeps every turn verbatim (138 meetings, 676,745 words) with BM25 and local embeddings over turn-aligned chunks. The *memory layer* holds typed items (decision, proposal, objection, action, figure, question, disagreement…) with speakers, verified quotes, and a relation to earlier items (`replaces`, `cancels`, `fulfils`, `resolves`…). Ingest reads each meeting **once, in order per team**, with the team's earlier memory as context, so "like we said last time" becomes a link to an item id. Questions go to a **bounded tool-use agent** (search memory, read a thread, search transcripts, read turns) that can only finish through `submit_answer`, which code accepts only when every quote is found word for word in one turn. **How it knows what is current:** meeting order is the clock; the model labels relations, and code (`memory.compute_state`) derives every status from them, rejecting links that point forward in time. The same rules replay any moment (`as_of`), which the TS3012 brief (built from meetings a–c only) and the UI's revision scrubber use.

**Model vs code.**

| Code, never a model | A model, and why |
|---|---|
| Parsing, ids, ordering, chunking, search, rank fusion | **Extraction:** knowing that "fine, let's go with that then" settles something, and what it replaces |
| Citation verification (the model is what's being checked) | **Agent:** choosing queries, reconciling meetings, wording the answer |
| What is current / superseded / open, from relations + order | **Brief prose:** readability only; code picks the facts and attaches the quotes |
| Speaker-role checks, loop budgets, retries, spend cap, scoring | |

**Tools and where they broke.** Python, the Anthropic Messages API with a hand-written tool loop (the control points are the product, so no framework), SQLite FTS5, local MiniLM, FastAPI. Claude Haiku 5.5 for everything, chosen for cost; Opus is one env var away.
1. *Low-effort extraction barely linked meetings* (1 superseded decision on a team that flip-flopped twice). Medium effort linked 3× more; a code rule files each linked item into its target's thread.
2. *Speaker letters aren't identities:* IS1000 swaps C and D between meetings. Fixed in code ("whoever says 'Right, Matthew?' isn't Matthew"); the first, broader version was wrong in 9 of 11 meetings and was caught by reading every change.
3. *One retrieval pass finds 44% of the evidence* (hybrid, k=5; BM25 alone 36%): the measured case for an iterating agent plus a memory layer.
4. *Rate limits* at 12 parallel extractions: 5 meetings failed and blocked their successors by design; backoff plus an idempotent resume finished them for $0.13.
5. *An agent dead-loop:* my error message didn't name the missing field and truncated tool calls weren't screened. Both fixed and tested.

**Results** (details in EVALUATION_REPORT.md). Catalist's 25: 25/25 answered, **70/70 citations verbatim-valid**, all 1–3 sentences, 23/25 citing ≥2 meetings, $0.04 in total. TS3012 brief: 34/34 citations valid. Our 12 hand-checked questions on other teams: **9 correct, 2 mostly correct, 1 wrong**. Three wrong: (1) TS3008 "who proposed the base": extraction merged the PM's "stand it up like a vase" into the proposal, and the agent trusted memory over transcript order; (2) IS1000 roles in meeting d, now fixed; (3) TS3005: a true but secondary answer that missed the PM's "unique idea".

**1,000 meetings** (measured on 134): ~15.5k input + 13.8k output tokens per meeting = **$0.0082 → ≈ $8.20 per 1,000** (≈ $4 batched), **≈ 3 h** at our rate limit, plus ≈ 1 h of CPU embeddings. Answers cost $0.0016 each. A stronger answering model (Sonnet 5.5) did not do better on our 12 checked questions (7 correct vs 9) at 12× the cost, so the bottleneck is memory quality, not answering. The whole build cost $1.94.

**Production at real scale.** Postgres + pgvector for concurrent writers and ANN search; a per-team-ordered job queue and the Batch API for backfills; retrieval over a team's threads instead of a fixed prior-memory window for long series; auth and audit; checked questions as a regression suite on every prompt or model change; and a review queue for low-confidence memory.
