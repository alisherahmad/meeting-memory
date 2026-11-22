---
version: 1
slug: "src-meeting-memory-static-index-html"
primary_target: "src/meeting_memory/static/index.html"
related_targets: ["src/meeting_memory/static/app.css","src/meeting_memory/static/app.js"]
---

# Meeting Memory web UI (Ask / Memory / Brief)

Mode: Operate. Audience: Catalist reviewers judging an Agentic AI build test, watching a recorded walkthrough or running it locally on a laptop; secondarily a founder's team before a meeting. Job: see what a team decided, what changed and when, and trace any line back to the exact words said. Constraints: plain static HTML/CSS/JS, no CDN or build step, all element ids, /api contracts and the accessibility behaviour pinned by tests/test_ui_accessibility.py stay intact.

User's edits to the chosen direction (quoted): "Replace the * column header ... Use a clear label like OPEN or a small flag/dot icon with a hover tooltip"; "Ensure the legend ... matches the exact row tints"; "Give each table row a light hover state ... and make rows clickable to open a slide-over drawer showing the exact transcript snippet".

## Direction contract

THESIS: A team's memory is a script under revision: every meeting issues a revision in its own page colour, so what changed and when reads from colour before a word is read. Refuses the category default of a SaaS card list with status badges.

OWN-WORLD: White script pages on a cool grey desk; revision tints a white, b blue #dbe7f7, c pink #f7dbe7, d yellow #f6eeb4 (the legend uses exactly these); ink #111418; revision red reserved for change marks only; amber for open items. Courier Prime only for the wordmark and slug lines (column heads, "REVISED TS3012d"); system sans for everything people read and operate; tabular figures; a 2px ink rule under the header.

STORY: The reviewer picks a team, sees each decision thread as one revision line tinted by the meeting that last changed it, reads what it was before, scrubs "Revision as of" to watch lines re-tint, and clicks any line to see the exact transcript words. Ask and Brief carry the same tints on their citations.

FIRST VIEWPORT: Memory view at 1440x900: header (wordmark, tabs, status), toolbar (team, revision-as-of a-d, show filter, colour legend), meeting revision strip, then the revision page: columns Topic | Current line with "Was:" history | Last revised | Status (labelled markers: Changed, Open action, Open dispute). Rows hover-tint and open the transcript drawer.

FORM: Revision Pages, position 1 on my ordered list (IMPECCABLE'S PICK, chosen by the user over the assigned position 4), seed:59797723a869002b. Signature interaction: scrubbing "Revision as of" re-tints each line to the revision that last touched it at that point (a short colour crossfade, none under reduced motion).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
