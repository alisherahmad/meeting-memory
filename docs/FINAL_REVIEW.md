# Final review (independent principal-engineer pass)

Reviewed: the repository at the final commit, `answers.json`, `evaluation/results/*`, and the running UI. I didn't take the implementation's docs on trust; each score cites evidence I checked.

## Scores
| Category | Score | Evidence |
|---|---|---|
| **Requirement compliance** | **9/10** | Every P0 in REQUIREMENTS.md has evidence: 138/138 ingested; 25 answers in the exact schema; 70/70 citations pass the verbatim check; brief with 4 sections, 34/34 valid citations, no leakage from TS3012d (`test_ingest_builds_time_aware_memory`); 12 own questions scored with 3 failures explained; measured cost/time for 1,000 meetings; model-vs-code table. Minus one: the one-page write-up runs about 1,000 words, and there's no recorded walkthrough video (live demo is the stated plan). |
| **Engineering quality** | **8/10** | Small, single-purpose modules; one SQLite file; status computed by a pure, tested function; every failure mode ends in a named state (55 tests, including all agent terminal states, truncated tool calls, backoff, spend cap). Real defects were found by testing and fixed (Q04 loop, strict-schema 400, rate limits). Minus: `extraction.validate_extraction` is long and does several jobs; prior-memory context is a fixed cap, not retrieval; SQLite single writer and brute-force dense search are explicit scale limits. |
| **AI quality** | **7/10** | Outputs are controlled (JSON schema, strict tool, code validation) and grounded (zero invalid citations across 70 + 34 + all gold runs). Measured: gold 9/12 correct by human read; hybrid retrieval beats either side. Minus: two systematic error types remain in memory: **role resolution** where letters swap (IS1000d), and **proposal conflation** (TS3008b), and the agent trusts memory over transcript order for "who first" questions. The gold set is 12 questions: a smoke test, not a benchmark. |
| **Product quality** | **7/10** | The UI is organised around the real workflows: live agent trace, citations that open the transcript at the highlighted turn, a decision timeline with "state as of" replay, and a brief view with a deterministic fallback. Inspected at desktop and 375 px, no console errors, keyboard-closable drawer. Minus: no authentication; long answers are dense; thread lists for large teams are long and lack search. |
| **Candidate ownership** | **8/10** (conditional) | ENGINEERING_WALKTHROUGH and INTERVIEW_PREPARATION map every claim to a file/function; decisions have recorded reasons, and the failure analysis is specific. The score depends on the applicant actually studying the six functions listed in INTERVIEW_PREPARATION ("Study these files personally"). |

## Five biggest remaining weaknesses
1. **Speaker roles can be wrong where letters change (IS1000d).** This affects any "who" question on such meetings. *Fixable:* deterministic vocative constraints ("Right, Matthew?" means the speaker isn't Matthew) and pass names, not previous mappings, to the extractor. Not done: it needs a name-identity layer, about half a day to do properly and test. Documented as failure 2.
2. **"Who first proposed X" depends on memory attribution.** Extraction can merge adjacent ideas (TS3008b). *Partly mitigated:* the agent is told to verify in transcripts, but it doesn't systematically compare timestamps across candidate items.
3. **Single-pass extraction quality is the ceiling for the brief.** The brief is built entirely from memory items, so a missed or mislabelled item is missing or wrong in the brief. Some brief citations support their point only loosely, because a point inherits the evidence of every item it groups.
4. **Small evaluation.** 12 gold questions with string-matched key facts plus one human reader. Confidence intervals are wide; one reviewer's judgment is a single point of failure.
5. **Scale limits are designed around, not built.** No Batch API path, no ANN index, a fixed prior-memory cap, a single SQLite writer, and CPU embeddings (≈1 h per 1,000 meetings).

## Fixed during this review
- Q04's 14-step dead loop (unactionable validation message + unscreened truncated tool calls) → fixed, tested, all 25 re-run.
- Over-length answers and system-internals leaking into answers → hard 3-sentence limit and format feedback; 23/25 now cite ≥2 meetings (was 15/25).
- An evaluation-report claim that the role error was a one-off → corrected: it's systematic.

## Verdict
Submit. The system does what the brief emphasises (scale-aware retrieval, explicit change tracking, a defensible model/code line, honest failure analysis), and it can't produce an unverifiable citation. Its known weaknesses are specific, reproducible and have concrete fixes, which is a better position for the interview than hiding them.
