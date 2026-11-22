# The 25 questions

**What they are.** Evaluation scenarios for the product's Q&A capability, scored by Catalist against held-back answers. They are not product requirements and not discovery questions. Every one names a team, needs at least two of its meetings, and asks for some combination of:

- **Δ change over time:** what was first chosen, what replaced it, when
- **@ attribution:** who said, proposed, objected or pushed (letter + role)
- **↻ commitment:** someone promised to find something out; what came back
- **# numbers:** prices, costs, totals, limits
- **? reason:** why something was kept, dropped or chosen

**How we treat them.** Original wording is preserved in `data/questions.json` and is never edited. There is no question-specific code, prompt, or keyword list (the brief says not to reverse-engineer the answers). The agent receives only the question text plus the team id. We validate automatically what we can check without the answers: citation format and verbatim validity, ≤3 sentences, and citing ≥2 meetings where the question spans meetings. We also read some answers next to their cited passages to find failures. Correctness against Catalist's answers can't be measured by us; our own gold set (`evaluation/gold_set.json`, disjoint teams) is the proxy.

**Components every question exercises:** team scope (`retrieval.team_from_text`) → `list_meetings` (per-meeting roles) → `search_memory`/`get_thread` (time-aware state) → `search_transcripts`/`read_turns` (verification and exact words) → `submit_answer` (code-verified citations).

| Q | Team | Tests | What makes it hard | Main components | Ambiguity / risk |
|---|---|---|---|---|---|
| Q01 | TS3006 | Δ ? : LCD vs speech recognition, which was cut, why the other was kept | The kept feature's *reason* may be stated in a different meeting from the cut | threads (cancels), transcript verification | Reason may be implicit |
| Q02 | ES2003 | Δ ? : case material first vs final, why switched | "Leaned towards" is softer than a decision; extraction must keep proposals | proposal → decision `replaces` | Lean vs decision boundary |
| Q03 | TS3009 | @ Δ : who first proposed replacing titanium, with what, was it kept | "First" needs chronological ordering across meetings; then the final status | code ordering (ordinal, seq), status | Several people may suggest alternatives |
| Q04 | TS3011 | Δ # : combined energy source and its fate after costing | Combination is two items; the costing is in a later meeting | figures + decision threads | — |
| Q05 | TS3007 | Δ @ : first energy source, final one, who proposed change | Attribution must be the letter *in the meeting where the change happened* | per-meeting roles | Letter/role mapping |
| Q06 | ES2008 | Δ @ ? : anti-loss feature, fate, main objector, objection | Back-references ("that beeper thing") without naming it | objection items, prior-memory linking | "Main" objection is a judgment |
| Q07 | IS1008 | ↻ # @ : who was asked to cost a display, what figure | Commitment in one meeting, report in another: needs `fulfils` linking | action_item → report | Figure may be spoken ("twelve fifty") |
| Q08 | ES2007 | @ ? : health complaint, who raised it, design response | Unusual topic (not a remote-control component); retrieval by paraphrase | hybrid retrieval, transcript search | Naming of the complaint |
| Q09 | IS1002 | # @ Δ : initial selling price, later range, who pushed for higher | IS1002 has no meeting `a`; "at first" = earliest available | ordinals from letters, figures | Missing first meeting |
| Q10 | TS3003 | ? : chosen age group and why | Reasoning spread over marketing presentation and discussion | decision + reason | Several age bands discussed |
| Q11 | ES2011 | ↻ ? : PM said they'd check a new requirement; question and answer | Commitment by PM; answer arrives in a later meeting | action_item `answers`/`fulfils` | — |
| Q12 | ES2004 | Δ ? : voice recognition as locator; fate; what still makes it findable | Three-part answer; the "still findable" part is a different feature | thread state + transcript | — |
| Q13 | TS3004 | Δ : speech recognition flip-flops; final state; meeting of last reversal | Several reversals; needs the *last* reversal, not the first | `reopens`/`replaces` chain, ordering | What counts as a "reversal" |
| Q14 | IS1009 | # ? : pending feature, final total, was it included | Status "pending" then a final costing | figure + decision, current status | Total may be quoted in parts |
| Q15 | ES2016 | # Δ : first full costing total, limit, removed component | Must choose the *first* full costing among several | ordering of figure items | Intermediate totals |
| Q16 | TS3010 | @ Δ # : PM's navigation control, its replacement, what else was given up | Two removals at the same time | thread changes in the same meeting | — |
| Q17 | ES2009 | Δ # : touch screen dropped in which meeting, kept feature, estimated cost | Meeting identification + figure | `cancels` item meeting id, figure | Estimate could be a range |
| Q18 | ES2014 | Δ @ : lost-remote plan, its change, who suggested presentation to buyers | Third part is about marketing framing, not the mechanism | items with speakers | — |
| Q19 | IS1003 | Δ @ : natural case material, replacement, who suggested the switch | Attribution in the switching meeting | per-meeting roles | — |
| Q20 | ES2008 | ↻ @ : TV-only buttons question; who looked into it; reported answer | Classic commitment → follow-up | action_item → report (`fulfils`) | Answer may be partial |
| Q21 | IS1007 | ↻ # Δ : who checked component prices; total with all functions; LCD decision | Three linked facts across ≥2 meetings | action_item, figure, decision | — |
| Q22 | ES2010 | @ ? Δ : who suggested lithium; who preferred what instead and why; final | Two people, two reasons, one outcome | proposal/objection items with speakers | — |
| Q23 | ES2006 | ? Δ : headline features kept vs swapped/simplified to meet budget | "Headline" is a judgment; multiple swaps | thread states at the final meeting | Open-ended list |
| Q24 | ES2002 | Δ @ : first agreed power source; addition the PM liked; final | Early agreement vs final state; PM attribution | thread chronology, roles | — |
| Q25 | ES2011 | ? Δ : fruit/vegetable shapes decision and why | Playful discussion; the decision may be implicit | proposals/rejections, reasons | Implicit decision |

**Cross-cutting acceptance criteria (applied to all 25):** answer every part of the question; ≤3 sentences; 1–3 citations, each verbatim from one turn of the named team's meetings; speakers given as letter + role for that meeting; where the question spans a change, cite both sides when possible.

**Our own scenarios.** The 12 gold questions (ES2005, ES2012, IS1000, IS1004, TS3005, TS3008) were written to the same five categories, with key facts and verified evidence quotes, and are scored by `python -m meeting_memory.evaluate gold`.
