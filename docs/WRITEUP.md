# Meeting Memory: one-page write-up

## Architecture
Two layers in one SQLite file. The **raw layer** holds every turn verbatim (48,148 turns, 676,745 words) with FTS5 and local MiniLM embeddings over ~220-word turn-aligned chunks. The **memory layer** holds typed items (decision, proposal, objection, action item, figure, requirement, question, report, disagreement), each with speakers, verified evidence quotes and a relation to earlier items (`replaces`, `cancels`, `fulfils`, `resolves`, `reopens`…), grouped into topic threads.

Ingest extracts each meeting **once**, in order per team. The extractor sees that meeting plus the team's earlier memory, so "like we said last time" becomes an explicit link to an item id. Questions go to a **bounded tool-use agent** (list meetings, search memory, read a thread, search transcripts, read turns, submit). It can only finish through `submit_answer`, and code accepts a submission only if every quote is found word for word in one turn of the named team's meetings. The TS3012 brief is built from the state **as of the end of meeting c**, so nothing from the meeting being prepared for leaks in.

**How it knows what is current:** meeting letters are the clock. The model only labels relations; code (`memory.compute_state`) derives every status from them: a decision is current until a later item replaces or cancels it, and an action is open until something fulfils it. Links pointing forward in time are rejected. The same rules replay any point in time (`as_of`), which the brief and the UI's "state as of" control use.

## Model vs code
| Never touches a model (code) | Uses a model, and why |
|---|---|
| Parsing, ordering, ids, chunking, BM25, embeddings + rank fusion | **Extraction:** deciding that "fine, let's go with that then" settles something, and what it replaces, is language understanding |
| Citation verification and repair (the model is what's being checked) | **Agent:** choosing queries and passages for open questions, reconciling meetings, wording 1–3 sentences |
| Status over time (current / superseded / open / done) from relations + order | **Brief prose:** readability only. Code picks the facts and attaches the quotes |
| Team scoping, loop budgets, retries, dedup, terminal states, spend cap | |
| Which facts enter the brief; legality of links (earlier only) | |
| Scoring our own gold set (string key facts + verbatim check) | |

## Tools, models, and where they broke
- **Python + Anthropic Messages API with a hand-written tool loop.** No agent framework: the loop's control points are the product. SQLite FTS5, numpy, FastAPI, local `all-MiniLM-L6-v2`.
- **Claude Haiku 5.5 for everything** (extraction, agent, brief), chosen for cost. Opus 5.5 is a one-line switch (`MM_AGENT_MODEL`).
- **Where it broke:**
  1. Low-effort Haiku linked meetings poorly (1 superseded decision found on TS3012, whose speech-recognition decision flipped twice). Medium effort linked 3× more, but opened new threads instead of joining the linked one. Fix in **code**: an item that replaces/fulfils X is filed in X's thread.
  2. Speaker letters are not identities (IS1000 swaps C/D between meetings c and d), so roles are resolved per meeting.
  3. CPU embeddings: 5,052 chunks took 503 s, the slowest ingest stage. At scale, embed on GPU or via an API.
  4. A single retrieval pass finds only 44% of gold evidence (k=5, hybrid; BM25 alone 36%). This is the reason for an iterating agent plus a memory layer.
  5. Rate limits: 12 parallel extractions × ~14k output tokens each hit 429s (5 of 121 meetings failed, blocking 8 later ones by design). Fix: 30/60/120 s backoff in ingest, then a resume pass at concurrency 4 that skipped finished work (13/13, $0.13).
  6. Agent loop: a run spent all 14 steps re-sending a malformed `submit_answer` because my error message didn't name the missing field, and truncated (`max_tokens`) tool calls weren't screened. Both fixed; `submit_answer` is now `strict` (whose schema rejects `maxItems`, a 400 caught on a single-question test).
  7. Operational: the project lives on an external SSD that disconnected mid-run. Per-meeting transactions + idempotent re-runs meant no corruption and no repeated spend.

## Results (details: EVALUATION_REPORT.md)
- **Catalist 25:** 25/25 answered; **70/70 citations verbatim-valid**; every answer 1–3 sentences with 1–3 citations; 23/25 cite ≥2 meetings. $0.041 for all 25, median 10 s each. Correctness is Catalist's to score.
- **TS3012 brief:** built from meetings a–c only; 4 sections; 34/34 citations valid.
- **Our 12 checked questions (6 teams not in the 25):** human read **9 correct, 2 mostly correct, 1 wrong**, plus a role error inside one otherwise-correct answer; 100% of citations valid.
- **Three wrong:** (1) TS3008: "who proposed the base". Extraction merged the PM's "stand it up like a vase" remark into the base proposal, and the agent trusted memory over transcript order. (2) IS1000 meeting d: the extractor carried the previous meeting's letter-to-role mapping across a swap the transcript reveals ("Right, Matthew?"). (3) TS3005: answered the "status before the final meeting" with a true but secondary fact and missed the PM's "unique idea".

## Cost and time for 1,000 meetings (measured on 134 meetings)
Extraction: ~15.5k input + ~13.8k output tokens per meeting on Haiku 5.5 = **$0.0082/meeting → ≈ $8.20 per 1,000 (≈ $4.10 with the Batch API)**. Wall clock: one call takes 70–100 s, but teams run in parallel; we sustained ~10 s/meeting at 12 concurrent before hitting rate limits, so **≈ 3 h per 1,000**, bounded by the output-token rate limit. CPU embeddings add ≈ 1 h (minutes on a GPU). Answering costs $0.0016 per question. The entire build, including pilots and three evaluation rounds, cost **$1.49**.

## What production would need at real scale
Postgres (FTS + pgvector) instead of SQLite for concurrent writers and ANN search; a job queue with per-team ordering for ingest and the Message Batches API (50% cheaper) for backfills; bounded prior-memory context via retrieval over a team's threads for long series; incremental re-extraction when a transcript is corrected (already cascades per team); auth, tenancy and audit on the API; a regression suite of checked questions run on every prompt or model change; and a human-review queue for low-confidence items (unverified quotes, inferred resolutions).
