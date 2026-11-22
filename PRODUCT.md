# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Catalist reviewers (primary audience for the UI).** They evaluate the Agentic AI Intern build test, run the app locally, and judge whether the system can be trusted: are citations real, does it know what changed over time, and can they see how the agent reached an answer.
- **Founder / team member (the end user the product is built for).** Someone whose team records every meeting. They need to find what was decided, what changed, who promised what, and who objected, without rereading hours of transcripts. Before a meeting they want a short brief.
- Secondary: an engineer inspecting memory state and agent behaviour, and an operator ingesting new transcripts (CLI only).

## Product Purpose
Meeting Memory turns meeting transcripts into time-aware memory you can question, and writes pre-meeting briefs. Success means a question gets a 1–3 sentence answer with 1–3 verbatim citations (meeting, turn, speaker, time), and a brief lists what is decided, what changed, open actions with owners, and open disagreements, every point cited.

## Positioning
Two claims, both load-bearing:
1. **Every quote is verified by code.** A citation is shown only if it appears word for word (at least 6 words, one speaker turn, ignoring case and spacing) in the transcript. The model never decides whether a citation is real.
2. **The memory knows time.** It tracks which decisions are current, superseded, cancelled, fulfilled or open, and shows *why* it believes meeting c overrode meeting a.

The system fails visibly instead of confidently: terminal states and unverified items are flagged, not hidden.

## Operating Context
- Corpus: 138 AMI meetings (676,745 words), grouped by team (e.g. ES2002, TS3012); meetings within a team are ordered a, b, c, d.
- Web UI (`python -m meeting_memory serve`, http://127.0.0.1:8765) has three views:
  - **Ask:** question + optional team, example questions, a live agent step trace, and the answer with citations that open the transcript in a drawer.
  - **Memory:** decision threads per team, viewed "as of the end of" a chosen meeting, filterable by status.
  - **Brief:** pick a team and the meeting being prepared for. Built only from earlier meetings, with model prose optional (deterministic fallback).
- CLI covers ingest, ask, answer-all (`answers.json`), brief, evaluate and stats.
- Speaker letters are per-meeting labels, not identities. Transcripts are real speech: disfluencies, overlaps, spoken numbers.

## Capabilities and Constraints
- **Architecture is fixed:** Python backend (`src/meeting_memory/server.py`) serving plain static HTML/CSS/JS from `src/meeting_memory/static/`. No framework, bundler or build step may be introduced.
- **Existing features and API contracts must keep working.** UI changes are incremental, not rewrites.
- **Frontend assets stay local:** no CDN fonts, scripts or external assets. The UI must load and render with no network.
- **Online features stay honest:** Ask and model-written briefs call the Anthropic API and need internet plus a key. The UI must not break them or imply they work offline. BM25 search, memory views and the deterministic brief work without a key.
- Local use only; no authentication or multi-tenancy (out of scope by design).
- Out of scope: audio and diarization, live transcript streaming, hand-editing memory.
- **Deadline: 23 November 2026.** Favour high-impact, low-risk improvements and reliability over ambitious redesigns.

## Brand Commitments
- Name: **Meeting Memory**. Built for Catalist; the Catalist name belongs to the client, not the product.
- Voice: plain, precise, unhyped. States what the system checked and what it couldn't, e.g. "Every answer is quoted from the transcript."

## Evidence on Hand
- `answers.json`: 25 submission answers with citations.
- `evaluation/gold_set.json`: 12 hand-checked questions; scored runs in `evaluation/results/`.
- Ingest reports (counts, quote-verification rate, tokens, cost) in `evaluation/results/ingest_report*.json`.
- Docs: `docs/ARCHITECTURE.md`, `docs/DECISION_LOG.md`, `docs/WRITEUP.md`, `docs/EXECUTION_STATUS.md`.
- Data: AMI Meeting Corpus (University of Edinburgh and partners, CC BY 4.0), reformatted by Catalist. Not committed.
- Absent, never fabricate: customers, testimonials, usage numbers, pricing, or accuracy figures not taken from the evaluation results.

## Product Principles
1. **Proof over claims.** Every answer shows its evidence: exact quote, speaker, meeting, time. Verification status is always visible.
2. **Time is first-class.** Current vs superseded, and the reason for the change, are shown, not just inferred.
3. **Fail visibly.** Errors, missing keys, unverified items and agent dead ends are surfaced plainly, never smoothed over.
4. **Show the reasoning.** The agent trace and the line between model judgment and deterministic code are open to inspection. That is what reviewers are judging.
5. **Reliable before ambitious.** Nothing ships that risks a working feature before the deadline.

## Accessibility & Inclusion
WCAG 2.2 AA: full keyboard operation (tabs, segmented controls, transcript drawer), visible focus, AA contrast in light and dark schemes, and `aria-live` updates for agent steps and answers. Desktop-first, but responsive down to narrow widths.
