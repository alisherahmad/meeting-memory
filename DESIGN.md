---
name: Meeting Memory
description: A team's meetings, kept as a script under revision, each meeting a page colour.
colors:
  desk: "#eceef2"
  page: "#ffffff"
  ink: "#111418"
  ink-2: "#3d4450"
  ink-3: "#565e6b"
  rule: "#dde1e7"
  rule-strong: "#b9bfc9"
  control-border: "#7b8391"
  revision-red: "#b3122e"
  revision-red-ink: "#ffffff"
  action: "#111418"
  action-ink: "#ffffff"
  current: "#14532d"
  current-bg: "#dcefe2"
  open: "#7a4a00"
  open-bg: "#fbecc8"
  gone: "#5a1622"
  gone-bg: "#f6e3e6"
  info: "#1e3a6e"
  info-bg: "#dde7f6"
  highlight: "#f6e08a"
  rev-a-white: "#ffffff"
  rev-b-blue: "#dbe7f7"
  rev-c-pink: "#f7dbe7"
  rev-d-yellow: "#f6eeb4"
  rev-e-green: "#dcefd9"
  rev-f-goldenrod: "#f3e0c4"
typography:
  wordmark:
    fontFamily: "Courier Prime, Courier New, Courier, monospace"
    fontSize: "24px"
    fontWeight: 700
    letterSpacing: "0em"
  headline:
    fontFamily: "Segoe UI, system-ui, -apple-system, Helvetica Neue, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    letterSpacing: "-0.01em"
  answer:
    fontFamily: "Segoe UI, system-ui, -apple-system, Helvetica Neue, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: "Segoe UI, system-ui, -apple-system, Helvetica Neue, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Segoe UI, system-ui, -apple-system, Helvetica Neue, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  slug:
    fontFamily: "Courier Prime, Courier New, Courier, monospace"
    fontSize: "13px"
    fontWeight: 700
  script-id:
    fontFamily: "Courier Prime, Courier New, Courier, monospace"
    fontSize: "13px"
    fontWeight: 400
  status-label:
    fontFamily: "Segoe UI, system-ui, -apple-system, Helvetica Neue, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 700
rounded:
  r: "4px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.r}"
    padding: "10px 24px"
  button-primary-hover:
    backgroundColor: "{colors.page}"
    textColor: "{colors.action}"
  button-ghost:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r}"
    padding: "4px 12px"
  tab:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    padding: "12px 16px"
  tab-selected:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
  segmented-option:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    padding: "7px 14px"
  segmented-option-checked:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
  input-field:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r}"
    padding: "8px 12px"
  status-label-current:
    backgroundColor: "{colors.current-bg}"
    textColor: "{colors.current}"
    typography: "{typography.status-label}"
    rounded: "{rounded.r}"
    padding: "2px 8px"
  status-label-open:
    backgroundColor: "{colors.open-bg}"
    textColor: "{colors.open}"
    typography: "{typography.status-label}"
    rounded: "{rounded.r}"
    padding: "2px 8px"
  status-label-gone:
    backgroundColor: "{colors.gone-bg}"
    textColor: "{colors.revision-red}"
    typography: "{typography.status-label}"
    rounded: "{rounded.r}"
    padding: "2px 8px"
  status-label-kind:
    backgroundColor: "{colors.info-bg}"
    textColor: "{colors.info}"
    typography: "{typography.status-label}"
    rounded: "{rounded.r}"
    padding: "2px 8px"
  revision-row:
    textColor: "{colors.ink}"
    padding: "12px 24px"
  citation:
    backgroundColor: "{colors.rev-a-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r}"
    padding: "12px 16px"
  transcript-drawer:
    backgroundColor: "{colors.page}"
    width: "min(680px, 100vw)"
---

# Design System: Meeting Memory

## Overview

**Creative North Star: "Revision Pages"**

A team's memory reads like a film or stage script under revision. Each meeting in a series issues a revision on its own page colour (a white, b blue, c pink, d yellow, then e green and f goldenrod), so what changed and when reads from colour before a word is read. White script pages lie on a cool grey desk; a 2px ink rule runs under the header and under every slug line, the way it would on a printed page.

The system is an operating tool, not a showcase. Density is moderate and tabular: one centred 1360px column, grid rows, tabular figures, short labelled markers. Revision red is the single loud colour and it means change. Everything people read and operate is set in the system sans; Courier Prime appears only where a script would use a typewriter face: the wordmark, slug lines (column heads, the revision header) and identifiers such as meeting ids and speaker labels.

Depth is paper: pages sit on the desk with a soft two-layer shadow, and the transcript drawer slides over the desk like a source page pulled from the stack. Motion is limited to state changes and the signature re-tint, and none of it runs under reduced motion.

**Key Characteristics:**
- Meeting = revision = page colour; the legend, rows, citations and history all use the same six tints.
- Revision red for change marks (and failure states); never decoration.
- Courier Prime for wordmark, slug lines and ids only; system sans for reading and operating.
- One colour for things you press: ink-filled when active or primary.
- Flat 4px corners everywhere; borders carry structure, shadows carry only paper.
- Every token pair is pinned for WCAG AA contrast in both colour schemes.

## Colors

A cool, nearly colourless desk and ink, with six pale revision tints carrying time and one saturated red carrying change.

### Primary
- **Revision Red** (revision-red): strikethrough lines on superseded wording, the "Changed" marker, the field-error message and invalid-field border, failed and superseded status labels, the over-budget status figure, and the textarea caret. In dark mode it lifts to a coral red.

### Secondary
- **Revision Tints** (rev-a-white through rev-f-goldenrod): the page colour of meeting a, b, c, d, e, f in a series. Applied as a background to revision rows (tinted by the meeting that last touched the line), the revision header, citation cards, "Was" chips, history rows, legend swatches and meeting cards. A meeting id ending in a letter without a tint falls back to white. The transcript turn being cited is set on the yellow tint with an ink border.

### Tertiary
- **Status pairs**: Current green (current / current-bg) for what is decided and standing; Open amber (open / open-bg) for open actions and open disputes; Gone wine (gone / gone-bg) as the badge default; Info navy (info / info-bg) for kind labels and tool-call steps. Each foreground is pinned at 4.5:1 on its own background.
- **Highlighter** (highlight): the `mark` on matched quote words and the text-selection colour.

### Neutral
- **Desk** (desk): the page background behind everything.
- **Page** (page): panels, header, tabs bar, revision page, drawer, controls.
- **Ink** (ink): primary text, the 2px rules, focus ring, and the fill of every pressed or primary control (via action).
- **Ink 2 / Ink 3** (ink-2, ink-3): secondary text, labels, metadata; ink-3 for the quietest text and placeholders, still 4.5:1 on desk and page.
- **Rule / Rule Strong** (rule, rule-strong): row dividers, and the edges of pages, cards, chips and swatches.
- **Control Border** (control-border): the edge of every interactive control (fields, segmented groups, ghost buttons, citation chips), pinned at 3:1 on desk and page.

Dark mode redefines every neutral, status and tint token under `prefers-color-scheme: dark` (values in the sidecar); tints become deep low-chroma versions of the same hues.

### Named Rules
**The Page Colour Rule.** A meeting's tint is its identity. Anything that comes from a meeting (row, citation, chip, history line, swatch) wears that meeting's tint, and the legend is generated from the same mapping so it always matches exactly.

**The Red Means Change Rule.** Revision red marks a change or a failure and nothing else. It is never a brand accent, a hover colour or a heading colour.

**The One Press Colour Rule.** Things you press are ink. Selected tabs, checked segments and the primary button are ink-filled with page-coloured text; there is no blue link or brand-coloured button.

**The Pinned Contrast Rule.** Colour tokens are hex values in `app.css` that tests/test_ui_accessibility.py parses and checks for WCAG AA in both schemes. Change a token only together with that test passing; de-emphasise with colour and dashed edges, never opacity.

## Typography

**Display Font:** Courier Prime (with Courier New, Courier, monospace), self-hosted woff2, 400 and 700
**Body Font:** System sans: Segoe UI (with system-ui, -apple-system, Helvetica Neue, Arial, sans-serif)
**Label/Mono Font:** Courier Prime for slug lines and identifiers

**Character:** A typewriter face stamps the script furniture (title, slugs, ids) while a plain system sans does all the reading, so the metaphor never costs legibility.

### Hierarchy
- **Wordmark** (Courier Prime 700, 24px): "Meeting Memory" in the masthead only.
- **Headline** (sans 700, 24px, -0.01em): the Brief title; empty-state headings at 20px.
- **Answer** (sans 500, 22px, line-height 1.45, max 62ch; 19px under 860px): the Ask answer sentence.
- **Body** (sans 400, 16px, line-height 1.55): revision lines, topics (700), transcript turns at 15px, brief items up to 78ch.
- **Label** (sans 600, 13px): field labels, legend, meeting-card text; section titles at 15px 700; tabs at 15px 600.
- **Slug** (Courier Prime 700, 13px, uppercase): revision-page column heads and Brief section heads (15px), each sitting on a 2px ink rule. The revision header names the revision in Courier 700 16px caps, e.g. "YELLOW REVISION · TS3012d", beside a 14px sans summary in ink-2.
- **Script id** (Courier Prime 400 to 700, 13 to 15px): meeting ids, "Was" chips, citation locations, speaker labels, history meeting ids, the drawer title.
- **Status label** (sans 700, 12 to 13px): badges and status markers.

### Named Rules
**The Typewriter Is Furniture Rule.** Courier Prime is for the wordmark, slug lines and identifiers. Never set sentences, answers, buttons or form text in it.

**The Tabular Figures Rule.** Counts, step numbers, turn numbers and the status bar use tabular numerals.

## Layout

Header, tabs and main content share one centred column of 1360px with a 32px inner gutter, so a single left and right edge run top to bottom. Spacing follows a 4px-based scale (s1 4px to s7 48px); panels pad at 24px, rows at 12px by 24px, gaps between controls at 12 to 24px.

- **Ask:** two columns, the question form (min 340px, 5fr) beside the answer (7fr).
- **Memory:** a wrapping toolbar (team, "Revision as of" segmented group, Show filter, colour legend pushed right), an auto-fit strip of meeting cards (min 230px), then the revision page with a four-column grid: Topic (1.1fr) | Current line with "Was" history (3.4fr) | Last revised (0.9fr) | Status (1fr).
- **Brief:** a single reading column; items capped at 78ch.
- **Under 860px:** gutters drop to 16px, Ask stacks to one column, the meeting strip and slug row hide (the legend already states each colour), the revision header switches to its one-line short form ("15 revised · 1 changed") and carries the 2px ink rule itself, revision rows stack with Last revised first and clamp the line to four lines and each "Was" to two, and the header status hides every figure except those whose value is a warning (missing key, incomplete memory).

## Elevation & Depth

Depth is paper on a desk. Pages (panels, the revision page, meeting cards) carry one soft two-layer shadow; everything inside a page is flat and separated by rules. The drawer is the only surface that lifts above the page, with a side shadow and a 32% ink scrim over the desk.

### Shadow Vocabulary
- **Page** (`box-shadow: 0 1px 2px rgba(17, 20, 24, .06), 0 8px 24px -12px rgba(17, 20, 24, .18)`): every page-level surface at rest.
- **Drawer** (`box-shadow: -16px 0 40px -16px rgba(17, 20, 24, .35)`): the open transcript drawer only; removed when it is hidden.

### Named Rules
**The Paper Only Rule.** Shadows describe sheets of paper, not interactivity. Hover is shown by an ink border or a 6% ink wash, never by lifting.

## Shapes

One radius: gently squared corners (4px) on panels, pages, controls, chips, badges and swatches; inner segmented buttons round only their outer ends. Tabs round their top corners only, sitting on the 2px ink rule. Status markers use a 10px dot (filled for most, a 2px ring for open disputes). Structure is drawn with 1px borders; emphasis rules are 2px ink; red strikethroughs on superseded wording are 1px. Future, not-yet-held meetings take a dashed edge.

## Components

### Buttons
- **Shape:** squared (4px).
- **Primary:** ink fill, page-coloured text, 1px ink border, 700 weight, 10px by 24px. Hover inverts to page fill with ink text (0.15s ease-out). Busy state: ink-3 fill with progress cursor.
- **Ghost:** page fill, control-border edge, 600 weight, 4px by 12px; hover darkens the edge to ink.
- **Focus:** every focusable element takes a 2px ink outline at 2px offset (inset 3px on full-width rows and the drawer body).

### Tabs
- Top-rounded label buttons on the page-coloured bar, 15px 600 in ink-2. Hover: ink text on a 6% wash. Selected: ink fill with page text, standing on the 2px ink rule.

### Segmented Radio Groups
- A single control-border outline holding options separated by 1px control-border dividers, 7px by 14px, 14px 600. Hover: 6% wash. Checked: ink fill, page text. No overflow clipping, so focus rings stay visible.

### Status Labels
- **Badges:** 12px 700, 2px by 8px, 4px corners, on the matching status pair: current green (current, answered, done, adopted, resolved), open amber (open, reopened, budget exhausted), red on gone-bg (superseded, cancelled, rejected, failed), navy on info-bg (kind).
- **Marks:** labelled dot markers in the revision row, 13px 700: Changed (red), Open action (amber dot), Open dispute (amber ring), Current (green), Noted (ink-2). Each carries a tooltip explaining it; the word is always present, never the dot alone.

### Inputs / Fields
- **Style:** page fill, 1px control-border edge, 4px corners, 8px by 12px; textarea min 104px at 16px with a revision-red caret.
- **Hover / Focus:** edge darkens to ink-2, then ink with the ink focus ring.
- **Error:** 2px revision-red border plus a 14px 600 red message tied to the field.

### Navigation
- The masthead: page-coloured bar with the three-page stacked brand mark (blue, pink, yellow sheets in ink outline), the Courier wordmark, a one-line subtitle, and the status figures (12px label over 14px 600 tabular value; warning values in revision red). The tabs bar sits directly beneath; both pad to the shared centred column. Under 860px the subtitle hides and the status keeps only its warning figures.

### Revision Page (signature)
- A page-coloured sheet with rule-strong edge and the page shadow. It opens with the **revision header**, which states the revision being viewed in Courier caps ("YELLOW REVISION · TS3012d") beside a sans summary line (lines revised, how many changed earlier decisions, lines shown). The **slug row** beneath sets the column heads in Courier caps. Header and slug row both take that revision's tint, so they read as one tinted block closed by the 2px ink rule. Under 860px the slug row hides and the header carries the rule.
- **Revision rows** are full-width buttons tinted by the meeting that last changed the line: bold topic, the current line, then up to two "Was" entries. Each "Was" opens with a Courier chip tinted by the meeting it came from ("Was, c pink", rule-strong edge, 4px corners), followed by the superseded wording struck through with a 1px revision-red line. Last revised shows the meeting id in Courier 700 over "turn N" in sans (never wrapped); status marks at the end. Hover lays a 6% ink wash over the tint; click opens the transcript drawer.
- **Re-tint:** scrubbing "Revision as of" (or changing the filter) for the same team keeps the mounted page in place, marked busy, and swaps the new page in when it lands, so each row animates from its previous tint to its new one where it sits (0.6s, cubic-bezier(.16, 1, .3, 1)); disabled under reduced motion.

### Legend and Meeting Cards
- **Legend:** one bordered swatch per meeting, tinted, with the Courier letter and the colour name ("b blue"), built from the same mapping as the rows.
- **Meeting cards:** tinted small pages with a Courier meeting id and "blue pages" note over one complete line, "roles · N turns"; the meeting's full summary is the card's tooltip, never a clipped sentence. Meetings after the chosen point become plain page-coloured cards with a dashed control-border edge, no shadow, ink-3 text and "not yet held". The strip hides under 860px.

### Citations
- **Citation card:** full-width button tinted by its source meeting, rule-strong edge, 12px by 16px; Courier location line above the 17px quote. Hover darkens the edge to ink.
- **Inline citation chip:** Courier 13px, tinted, control-border edge, opens the same drawer.

### Transcript Drawer
- A page slid in from the right (up to 680px), 0.25s cubic-bezier(.16, 1, .3, 1), over a scrim. Courier title with meeting and turn over a 2px ink rule; optional revision history list (tinted rows, Courier ids, 1px red strikethrough for superseded wording); transcript turns in a 78px Courier speaker column. The cited turn is set on the yellow tint with an ink border and its matched words highlighted. Modal: focus trapped, Escape closes, focus returns.

## Do's and Don'ts

### Do:
- **Do** tint anything that comes from a meeting with that meeting's revision tint, and derive the legend from the same mapping.
- **Do** keep revision red for change marks, superseded strikethroughs and failure or error states.
- **Do** set the wordmark, slug lines and ids in Courier Prime, and everything people read or operate in the system sans.
- **Do** put a 2px ink rule under the header and under each slug line; where the slug line is hidden, the element above it carries the rule.
- **Do** keep every control edge on control-border (3:1) and every text pair at 4.5:1 in both schemes; run tests/test_ui_accessibility.py after any token change.
- **Do** self-host every font and asset; no CDN and no build step.
- **Do** de-emphasise with colour and dashed edges, and disable all animation and transition under reduced motion.

### Don't:
- **Don't** use revision red as an accent, a hover colour or decoration.
- **Don't** set body text, answers, buttons or form fields in Courier Prime.
- **Don't** use opacity to fade content; it drops text below AA.
- **Don't** put overflow clipping on segmented groups; it hides focus rings.
- **Don't** show a status as a dot alone; every marker carries its word.
- **Don't** add a second press colour; pressed and primary controls are ink.
