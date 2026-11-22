# Source ledger

What Catalist supplied, what each source says, and what we did about it. Precedence when sources disagree: (1) the PDF brief, (2) `questions.json` instructions (Catalist's own clarifications), (3) the email, (4) data and examples, (5) our inference.

## Inventory (inspected 2026-11-22)

| File | Size | Status | Notes |
|---|---|---|---|
| `Catalist_Agentic_AI_Intern_Build_Test.pdf` | 122 KB, 2 pages | Read in full (text and rendered pages) | The brief. No diagrams beyond the JSON example. |
| `Catalist_AI_Intern_Build_Test_Data.zip` | 1.5 MB, 140 entries | Listed before extraction, then extracted to `data/` (original untouched) | 138 transcripts + `questions.json` + `CREDITS.txt` |
| `data/transcripts/*.txt` | 138 files | All parsed by code. Read by hand: TS3012a–d in part, plus targeted passages. 12 further meetings (ES2005, ES2012, IS1000, IS1004, TS3005, TS3008) read in full by the gold-set authors | 676,745 words by our parser (the brief says "about 676,000"), 48,148 turns, speakers A–D only |
| `data/questions.json` | 8 KB | Read in full | 25 questions + extra instructions (see Q-rows below) |
| `data/CREDITS.txt` | 329 B | Read | AMI corpus, CC BY 4.0; "words are as transcribed; non-speech markers are left out" |
| Email (screenshot) | n/a | Read | Deadline 23 Nov 2026; "AI coding tools are fine; we care that you understand what you built" |

No file was inaccessible, corrupt or password-protected. **Honest limit:** nobody read all 676k words by hand. The system reads all of it; humans read the parts the questions and gold set needed.

## Requirements by source

| ID | Source and location | Original wording (extract) | Interpretation | Confidence | Consequence |
|---|---|---|---|---|---|
| S1 | PDF p1 "The problem" | "turns a large set of real meeting transcripts into memory you can ask questions of, and that briefs a team before its next meeting" | Two products: Q&A over memory, and a pre-meeting brief | explicit | `agent.py`, `brief.py` |
| S2 | PDF p1 "The data" | "Treat the transcripts as a store you retrieve against, not something you paste into a prompt … 10,000 meetings … An approach that only works because everything fits in one context window is the wrong answer." | No whole-corpus prompts. Retrieval must be scoped and indexed. Per-meeting processing is fine | explicit | SQLite FTS5 store; agent sees only tool results; extraction is one call per meeting |
| S3 | PDF p1 "What the agent must do" 1 | "Ingest the meetings into a memory store your agent can search." | Persistent searchable store | explicit | `store.py`, `ingest.py` |
| S4 | PDF p1, 2 | "each in a sentence or two, with one to three citations: the meeting id and the exact words … Citations are checked word for word." | Short answers; 1–3 citations; verbatim | explicit | `submit_answer` contract + code verification (`quotes.py`) |
| S5 | PDF p1, 3 | "the brief Team TS3012 should read before their final meeting: what has been decided, what changed along the way, open actions and who owns them, and disagreements still open. Cite each point." | Brief with 4 sections, every point cited | explicit | `brief.py` with the 4 sections; uncited points dropped |
| S6 | PDF p1 JSON | `{"answers":[{"question_id","answer","citations":[{"meeting_id","quote"}]}],"brief":"…"}` | Output schema | explicit | `cli.py answer-all` writes exactly this shape |
| S7 | PDF p1 "assessing" | "retrieve, loop, process in steps; an architecture that wouldn't fall over at 10,000 meetings" | Multi-step tool loop; scale story | explicit | Bounded tool loop; scale section in the write-up |
| S8 | PDF p1 "assessing" | "a decision in meeting c can replace one from meeting a, and people refer back to things without naming them. Show how your agent knows what is current." | Time-aware memory: supersession and back-references | explicit | Threads + relations + `memory.compute_state` (code); prior-memory context during extraction; Memory view "as of" slider |
| S9 | PDF p2 | "draw the line yourself between what a model decides and what plain code does … Some of this work should never touch an LLM. Tell us which, and why" | Explicit model-vs-code boundary | explicit | DECISION_LOG + write-up table |
| S10 | PDF p2 | "write at least 10 questions of your own, with answers you checked by reading the transcripts, score your agent on them" | Own gold set ≥ 10 | explicit | `evaluation/gold_set.json` (12 cases, disjoint teams) + `evaluate.py gold` |
| S11 | PDF p2 | "Tell us what ingesting 1,000 meetings would cost and how long it takes." | Measured cost/time extrapolation | explicit | LLM call ledger (`llm_calls` table) → EVALUATION_REPORT |
| S12 | PDF p2 | "give us three questions your agent got wrong and explain why" | Failure analysis | explicit | EVALUATION_REPORT |
| S13 | PDF p2 | "which framework, models and APIs you chose, why, and where they broke at this size" | Platform reasoning | explicit | WRITEUP + DECISION_LOG |
| S14 | PDF p2 "What to submit" | "Code and a README … Your answers.json, made by your agent … A write-up of about one page … A 3 to 5 minute walkthrough recording, or come ready to demo live … a few new questions to run live" | Deliverables; the system must take unseen questions live | explicit | README, `answers.json`, `docs/WRITEUP.md`, CLI `ask` + web UI |
| S15 | PDF p2 | "We are holding back the answers … don't try to reverse-engineer them." | Do not tune on or hand-answer the 25 | explicit | No question-specific code or prompts; gold set uses other teams |
| S16 | PDF p2 | "Judgment over polish … Keep it to roughly a day." | Scope discipline | explicit | Small architecture, plain web UI |
| Q1 | questions.json `instructions[0]` | "decisions and how they change over time, who said what, commitments and whether they were followed up, and numbers" | Four memory dimensions to support | explicit | Item kinds: decision, action_item/report (follow-up), figure, speakers on every item |
| Q2 | `instructions[2]` | "Every question needs at least two meetings of the named team. Answer each one in one to three plain sentences." | Team-scoped, multi-meeting; ≤3 sentences | explicit | Team scope from the question; agent told to check later meetings |
| Q3 | `instructions[3]` | "Give the letter, and the role too if the transcripts make it clear." | Speaker letter + role | explicit | Per-meeting role resolution (`roles.py` + extraction) |
| Q4 | `instructions[4]` | "a quote of at least six words copied exactly from that transcript, from within one speaker turn … (case and spacing are ignored); paraphrases fail" | ≥6 words, single turn, case/space-insensitive | explicit | `quotes.MIN_QUOTE_WORDS=6`; whole-token single-turn matching; we emit exact substrings |
| Q5 | `brief_task` | "Write the brief Team TS3012 should read before their final meeting." | Brief uses meetings a–c only | strongly implied | `generate_brief(before=TS3012d)` computes state as of the end of c; d is excluded so nothing leaks from the meeting being prepared for |
| D1 | Data (IS1000 c→d; found by gold-set author) | Letters C and D swap identities between IS1000c and IS1000d | Letters are not stable person ids across meetings | explicit in data | Roles resolved per meeting, never per team |
| D2 | Data | IS1002 and IS1005 have 3 meetings (IS1002 lacks `a`) | Series can be incomplete; "final meeting" = last present | explicit in data | Ordinals come from the letter, not position; brief default = team's last stored meeting |

## Conflicts and how they were resolved

1. **Citation count vs "cite each point"** (PDF: 1–3 citations per answer; brief: cite each point). These don't conflict, because they apply to different outputs. Answers are capped at 3 citations by schema. Brief points carry 1–3 citations each.
2. **"Exact words" vs "case and spacing are ignored".** The more specific rule wins (questions.json). We go further: every quote we emit is an exact character substring of the transcript, so it passes whether or not punctuation is compared.
3. **"Before their final meeting" could mean "using everything up to and including d".** We chose the conservative reading: a brief read *before* meeting d cannot contain d. The CLI's `--before` flag makes the other reading a one-flag change.
