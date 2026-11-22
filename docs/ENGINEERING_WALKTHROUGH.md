# Engineering walkthrough

Read this with the code open. File and function names are real.

## 1. The problem
138 meeting transcripts (676,745 words). Two outputs: answers to questions that need several meetings, with verbatim citations; and a brief for TS3012 before its final meeting. The brief's hidden test is **time**: decisions change, people refer back without naming things, and the system must know what is current. The constraint is **scale**: design for 10,000 meetings, so no "paste everything into the prompt".

## 2. Product workflow
`ingest` once (and again whenever meetings arrive) → `ask` / `answer-all` / `brief` / web UI. Ingest builds two layers in one SQLite file:
- **Raw layer:** every turn, verbatim. This is the source of truth for citations.
- **Memory layer:** typed items (decision, proposal, objection, action_item, figure, requirement, question, report, disagreement) grouped into topic threads, with relations to earlier items.

## 3. Architecture in one paragraph
Code parses, indexes and searches. A model reads each meeting once, with the team's earlier memory as context, and writes structured items and links. Code validates the links, verifies every quote, and computes what is current. At question time, a model drives a bounded loop of read-only tools; code validates every call and only lets the run end with citations it has verified against the stored turns. Diagrams: ARCHITECTURE.md.

## 4. Components (in the order a request touches them)
- **`transcripts.parse_transcript`**: header lines then `HH:MM:SS Speaker X` turns. `Meeting.ordinal` comes from the letter (a=1), which is the system's clock. `content_hash` drives idempotency.
- **`chunking.chunk_meeting`**: ~220-word windows that start every ~110 words and never split a turn. Each chunk keeps `start_idx..end_idx`, so the agent can `read_turns` around a hit.
- **`store.Store`**: schema in `SCHEMA`. `chunks_fts` and `items_fts` index `team` as a column, so `team:"ts3012" AND text:(…)` is an index lookup. `fts_query` quotes every term, so user text can't inject FTS syntax.
- **`roles.detect_self_introductions`**: regex for "I'm the Project Manager"-style turns; a role claimed by two speakers in one meeting is dropped. `merge_roles` prefers regex over model claims. Roles are per meeting, because letters aren't stable (IS1000 c→d swaps C/D).
- **`retrieval.Retriever`**: `search_chunks` fuses BM25 and MiniLM cosine ranks with Reciprocal Rank Fusion (`_rrf`, k=60). Dense ranking is brute force over the *filtered* set.
- **`extraction.extract_meeting`**: builds the prompt from `render_prior_state(compute_state(earlier items))` + `render_participants` + the numbered transcript. Calls `LLM.json_call` with `EXTRACTION_SCHEMA` (structured output). Then **`validate_extraction`** does the real work: enum checks; thread ids must exist or be `new:<key>`; `related` ids must be earlier items (or `@k` earlier in the same meeting); speakers must be present; every evidence quote goes through `resolve_quote`; role claims must quote the claimed speaker's own turn. Unverifiable items are kept with `verified=False` and are never cited.
- **`memory.compute_state`**: pure function. It walks items in (ordinal, seq) order and applies relations: `replaces` → superseded, `cancels` → cancelled, `fulfils` → done, `resolves` → resolved, `adopts` → adopted… An implicit `replaces` targets the thread's current decision. A later decision in the same thread closes open disagreements, marked `inferred=True` so it's never presented as said. `as_of_ordinal` filters history first.
- **`ingest.run_ingest`**: parse → embed chunks → extract per team in order (`_extract_team`), teams in parallel → embed items. If meeting k fails, k+1.. are `blocked`. Re-extracting k first runs `clear_team_memory_from(team, k)`.
- **`agent.Agent.answer`**: the loop (section 6).
- **`tools.ToolBox`**: `list_meetings`, `search_memory`, `get_thread`, `search_transcripts`, `read_turns` (≤40 turns), and `verify_submission`. Arguments are pydantic models; results are compact text.
- **`brief.generate_brief`**: `build_digest` (code) picks verified items by status as of meeting N−1; the model writes `BRIEF_SCHEMA` sections that may only reference digest ids; `_citations_for` attaches the stored quotes; points with no citation are dropped. Without a model, a deterministic version is rendered from the digest.

## 5. Important data structures
- **Item:** `{item_id: "TS3012b-007", meeting_id, ordinal, seq, kind, thread_id: "TS3012a-T03", relation, related: [...], topic, statement, speakers: ["B"], owner, value, evidence: [{meeting_id, turn_idx, speaker, time, quote}], verified}`
- **ItemState / ThreadState** (`memory.py`): the item plus `status`, `by` (which later items caused it) and `inferred`.
- **AgentResult** (`agent.py`): `state ∈ {answered, answered_partial, budget_exhausted, failed}`, answer, citations (with `turn`, `speaker`, `time`, `method`), steps, tool_calls, trace, usage.

## 6. How a question is processed
1. `team = team or team_from_text(question)`; `ToolBox(scope_team=team)`.
2. Each step: `LLM.create(model, effort, system=AGENT_SYSTEM (cached), tools=TOOL_DEFS, messages)`.
3. A `refusal` ends the run. Prose without a tool call gets one nudge ("call submit_answer"), and that still counts as a step.
4. Each `tool_use` is checked against the `cache` (identical name+args returns the earlier result), dispatched with validated args, traced, and all results go back in **one** user message. Two steps before the limit, a text block says "call submit_answer now".
5. `submit_answer` → `_handle_submit` → `verify_submission`: team check, meeting exists, `resolve_quote` (exact → relocated → repaired, unique-only). All verified → `answered`. Otherwise the failures are reported back; after `max_submit_rejections` (2), the verified subset is kept (`answered_partial`).
6. Step budget (14) or wall clock (300 s) → `budget_exhausted`, keeping the last verified submission if there was one.

## 7. How the AI components work
- **Extraction:** Opus 5.5, adaptive thinking (always on for this model), `effort=medium`, structured output (`output_config.format` JSON schema), streaming, max 48k output tokens. System prompt cached.
- **Agent:** Opus 5.5, `effort=medium`, 6 client tools, parallel tool calls allowed, system + conversation cached (`cache_control`), server-side refusal fallback.
- **Embeddings:** local `all-MiniLM-L6-v2` (384-d), offline.

## 8. How external tools are invoked
Only one external service: the Anthropic Messages API, via `llm.AnthropicBackend` (beta endpoint, solely to opt into `fallbacks`). Typed SDK errors are mapped to `LLMError`/`LLMUnavailable`. Every call writes a row to `llm_calls`.

## 9. How state is managed
- **Persistent:** SQLite (`var/memory.db`): turns, chunks, items, threads, roles, ledger.
- **Derived on read:** item status (`compute_state`), never stored, so it can't go stale.
- **Per-run:** the agent's `messages`, tool-call cache, and trace. Nothing carries over between questions (no hidden conversational "memory").
- **Per-ingest:** `IngestReport`.

## 10. How failures are handled
See the table in ARCHITECTURE.md. The principle: every failure ends in a named state that is visible in the CLI output, the trace, the UI, or the ingest report. Nothing fails silently, and nothing unverified is cited.

## 11. How it is tested
- `tests/` (43 tests, ~12 s, no network): parsing; quote verification incl. cross-turn rejection and repair; time-aware state (supersede, as-of replay, forward-link rejection, fulfil, inferred resolution); extraction validation; ingest end to end with a fake model (idempotency, failure cascade, no-key mode); every agent terminal state; duplicate and invalid tool calls; cross-team citations; refusal; server endpoints and input validation.
- `evaluate.py retrieval`: recall of gold evidence passages for BM25 / dense / hybrid.
- `evaluate.py gold`: the agent on 12 hand-checked questions; key facts + verbatim citations.
- `evaluate.py check-answers`: grader emulation on `answers.json` and the brief.

## 12. Trade-offs worth defending
- **Structured memory at ingest** costs one model call per meeting, and buys change tracking that code can reason about. The agent still verifies in raw text.
- **Sequential per-team extraction** is slower inside a team but resolves back-references in the same call.
- **Code-only citation verification** makes the system unable to invent a quote, but a strict verifier will sometimes reject a quote a lenient grader would accept. We optimise for zero invalid citations.
- **SQLite + brute-force dense search** is simple and fast at this size, with a clear swap path at 10k+.
- **No framework** means more code we own (~1.5k lines), but every control point is visible.
