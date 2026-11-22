# Decision log

## D1 — Model vs code: where the line is
| Step | Owner | Why |
|---|---|---|
| Parsing files, turn ids, timestamps, team/meeting ids, ordering | **Code** | Deterministic format; an LLM adds cost and error with zero benefit |
| Chunking, indexing, BM25, embeddings, rank fusion | **Code** (+ small local model) | Mechanical; must be reproducible and cheap at 10k meetings |
| Scoping a question to a team | **Code** (regex on the question; the CLI passes the team) | Exact ids; never worth a model call |
| Citation verification and repair | **Code, always** | Graded word for word. The model is the thing being checked, so it can't be the checker |
| Speaker roles from explicit self-introductions | **Code** (regex), backed by model claims that must quote the speaker's own turn | High-precision rule first; the model covers implicit cases (names, who presents what) |
| What happened in a meeting (decision vs proposal vs objection, reasons, commitments) | **Model** | Language understanding over disfluent speech ("fine, let's go with that then") |
| Linking a new statement to an earlier one ("replaces", "fulfils") | **Model** | Back-references without naming things are exactly what rules can't resolve |
| Whether a link is legal (target exists, earlier in time) | **Code** | A model must not be able to rewrite history |
| What is current / superseded / open / done | **Code** (`memory.compute_state`) | Given the links, status is a pure function of order; it should be testable without an LLM |
| Which tools to call, which passages are relevant, the answer wording | **Model** | Open-ended search over ambiguous questions |
| When the loop stops; budgets; retries; duplicate calls | **Code** | Control flow must be bounded and observable |
| Which facts go in a brief | **Code** (state as of meeting N−1, by status) | No leakage from the future, no invented facts |
| Brief prose | **Model** (optional) | Readability; it may only cite digest item ids, and code attaches the quotes |
| Scoring our gold set | **Code** (key-fact strings + verbatim check), plus a human read | LLM-as-judge would grade the model with the model; we used plain checks and our own eyes |

## D2 — Python, no agent framework
Considered LangChain/LangGraph and LlamaIndex. Rejected: the loop is ~150 lines, and owning it gives exact budgets, verification at the exit, and readable traces, which are the things being assessed. A framework would hide the control flow I need to defend.

## D3 — Anthropic Messages API, self-hosted manual tool loop (not Managed Agents, not the SDK tool runner)
The memory store is local SQLite and the loop's control points (verified `submit_answer`, budgets, dedup, terminal states) are part of the product. Managed Agents would host the loop remotely and bill session time; the beta tool runner hides the exit condition. Streaming is used so long extraction outputs don't time out. Server-side refusal fallback (`fallbacks: "default"`) is enabled on the beta endpoint.

## D4 — Models
Default `claude-opus-5-5` for both extraction and the agent (configurable via `MM_EXTRACT_MODEL`, `MM_AGENT_MODEL`). Effort `medium` (Opus 5.5's default) for both. Extraction is the dominant cost at scale. `claude-haiku-5-5` is ~40× cheaper per token and is the obvious lever for a 10k-meeting backfill, but its extraction quality has not been measured here, so it isn't the default (see EVALUATION_REPORT for the cost comparison).

## D5 — SQLite + FTS5 (+ optional embeddings in the same file)
One file, zero ops, transactional, BM25 built in. FTS5 has an indexed `team` column so scoped search uses the index. Embeddings are float32 blobs ranked with numpy over the filtered set. Rejected: a separate vector DB (another service to run for a 5k-chunk corpus). Production swap: Postgres + pgvector.

## D6 — Structured memory extracted at ingest, not only chunk RAG
Chunk RAG alone can't answer "what is current" without re-reading every meeting at query time. Extracting typed items with relations once per meeting turns change tracking into a data problem code can reason over. Cost: one model call per meeting, paid once. The agent still verifies in the raw transcript, because memory is an index, not the source of truth.

## D7 — Incremental extraction with prior memory as context (vs. extract each meeting independently, then link)
Independent extraction would need a second, team-wide linking pass and couldn't use earlier context to interpret "that idea from last time". Sequential-per-team extraction mirrors production (meetings arrive in order) and links in the same call. Trade-off: within a team, ingestion is serial, and a failure blocks later meetings (by design).

## D8 — Roles per meeting, not per team
The data showed letters aren't stable (IS1000: C and D swap between meetings c and d). Roles are resolved per meeting and shown that way to the agent.

## D9 — Quote repair is deterministic and conservative
Models drop "um"/"uh" or punctuation when copying. `resolve_quote` aligns tokens and cuts the exact span from the transcript, only if the alignment is strong (≥85% of tokens, span ≤1.25× the quote length) and unique. The emitted quote is always transcript text, never the model's.

## D10 — Brief "before their final meeting" uses meetings a–c only
A brief read before meeting d can't know d. Implemented via `as_of_ordinal`; `--before` lets a user choose otherwise.

## D11 — Plain web UI (FastAPI + static HTML/JS), no build step
The brief values judgment over polish. A small, honest UI that shows the agent's real steps and the memory's time dimension is more useful to a reviewer than a framework app.

## D12 — Gold set authored on teams disjoint from the 25 questions
Prevents leaking hand-found answers into the scored set or tuning on it. Two parallel authors (subagents) read 12 meetings in full; every evidence quote is re-verified by `evaluate.py build-gold`.

## Decisions intentionally not made
- No LLM-as-judge as the primary metric (circular).
- No cross-encoder reranker (measure first; agent iteration compensates).
- No global entity resolution of people across meetings (letters + roles per meeting are what the grader asks for).
- No auth / multi-user (local tool; would be the first production addition).
