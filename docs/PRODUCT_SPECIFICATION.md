# Product specification

## The problem
A founder records every meeting. Months later, nobody can find what was decided, what changed, who promised what, or who objected. And nobody reads hundreds of hours of transcripts before the next meeting. The product must turn transcripts into **memory**: searchable, aware of time, and trustworthy because every claim points to the exact words said.

## Users and workflows
| User | Workflow | Input | Output |
|---|---|---|---|
| Founder / team member | Ask a question about past meetings | Natural-language question, optionally a team | 1–3 sentence answer + 1–3 verbatim citations (meeting id, turn, speaker, time) |
| Team before a meeting | Read a brief | Team + the meeting being prepared for | Decided / changed / open actions with owners / open disagreements, each point cited |
| Reviewer / engineer | Inspect memory and behaviour | Team, point in time | Decision threads with current vs superseded status; the agent's step-by-step tool trace |
| Operator | Ingest new meetings | Transcript files | Idempotent, incremental ingest with a report (counts, quote verification rate, tokens, cost) |

## What the system decides
1. **Which passages matter** for a question. The agent does this via search tools.
2. **What a meeting said:** decisions, proposals, objections, commitments, figures, requirements, questions, reports, disagreements. The model extracts these, once per meeting.
3. **How a new meeting relates to the past:** replaces, cancels, fulfils, resolves… The model labels it; code enforces time order.
4. **What is current.** Code derives this from the relations and meeting order.
5. **Whether a citation is real.** Code always decides this.

## Constraints
- Corpus is "a runnable slice" of 10,000+ meetings: no whole-corpus prompts; per-team scoping; index-backed search.
- Citations are machine-checked word for word (≥6 words, one turn, case/spacing-insensitive).
- Speaker letters are per-meeting labels, not identities (IS1000 swaps C/D between meetings c and d).
- Real speech: disfluencies, overlaps, spoken numbers ("twelve fifty").

## Acceptance criteria
- `answers.json` with 25 answers, each 1–3 sentences with 1–3 citations, **100% of citations verbatim-valid**.
- TS3012 brief built only from meetings a–c, four sections, every point cited and verbatim-valid.
- ≥10 own questions with checked answers, scored, with failures explained.
- Measured ingest cost/time, extrapolated to 1,000 meetings.
- New questions can be run live (CLI and UI) with no question-specific code.

## What separates acceptable from excellent
Acceptable: RAG over chunks that returns plausible answers. Excellent:
- knows that meeting c overrode meeting a, and shows *why it believes so*;
- never emits a quote that isn't in the transcript;
- fails visibly (terminal states, unverified items flagged) instead of confidently;
- has a clear, defended line between model judgment and deterministic code;
- reports its own errors with root causes.

## Out of scope (deliberately)
Authentication and multi-tenancy, audio and diarization, live transcript streaming, editing memory by hand, and anything not needed for the brief's deliverables.
