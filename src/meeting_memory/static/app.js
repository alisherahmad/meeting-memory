// Meeting Memory UI. Vanilla JS; all transcript-derived text is inserted with
// textContent (never innerHTML) because transcripts are untrusted input.

const $ = (sel) => document.querySelector(sel);

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return res;
}

const badge = (text, cls = text) => h("span", { class: `badge ${cls}` }, text.replace(/_/g, " "));
const prettyKind = { tool_call: "tool call", tool_result: "result", submit_rejected: "quote rejected", submit_accepted: "verified", note: "note", error: "error" };

let TEAMS = [];

// ---------- Tabs ----------
const tabs = ["ask", "memory", "brief"];
function selectTab(name) {
  for (const t of tabs) {
    const on = t === name;
    $(`#tab-${t}`).setAttribute("aria-selected", on);
    $(`#tab-${t}`).tabIndex = on ? 0 : -1;
    $(`#view-${t}`).hidden = !on;
  }
  if (name === "memory" && !$("#threads").childElementCount) loadMemory();
  history.replaceState(null, "", `#${name}`);
}
tabs.forEach((t, i) => {
  const b = $(`#tab-${t}`);
  b.addEventListener("click", () => selectTab(t));
  b.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      selectTab(next); $(`#tab-${next}`).focus();
    }
  });
});

// ---------- Status ----------
async function loadStatus() {
  try {
    const s = await (await api("/api/status")).json();
    const st = $("#status");
    st.replaceChildren(
      h("div", {}, h("dt", {}, "Meetings"), h("dd", {}, s.meetings)),
      h("div", {}, h("dt", {}, "Words"), h("dd", {}, s.words.toLocaleString())),
      h("div", {}, h("dt", {}, "Memory"), h("dd", { class: s.extracted < s.meetings ? "warn" : "" }, `${s.extracted}/${s.meetings} meetings · ${s.items_verified.toLocaleString()} items`)),
      h("div", {}, h("dt", {}, "Search"), h("dd", {}, s.chunks_embedded ? "BM25 + embeddings" : "BM25 only")),
      h("div", {}, h("dt", {}, "Model"), h("dd", { class: s.llm_available ? "" : "warn" }, s.llm_available ? s.agent_model : "no API key")),
    );
  } catch (e) {
    $("#status").textContent = `Status unavailable: ${e.message}`;
    announce(`Status unavailable: ${e.message}`, { urgent: true });
  }
}

// ---------- Announcements ----------
// One polite region (#announcer) for outcomes, one assertive region (#alerter)
// for failures. Results panels are not live regions: they would read the whole
// answer, every citation and the cost line in one go.
function announce(msg, { urgent = false } = {}) {
  const el = $(urgent ? "#alerter" : "#announcer");
  el.textContent = "";
  // Clear, then set after a tick, so a repeat of the same message is re-announced.
  setTimeout(() => { el.textContent = msg; }, 60);
}
const setBusy = (el, busy) => el.setAttribute("aria-busy", String(busy));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// ---------- Transcript drawer (modal dialog) ----------
const BACKGROUND = ["header.masthead", "nav.tabs", "main"];
let lastFocus = null;
const drawerOpen = () => $("#drawer").getAttribute("aria-hidden") === "false";
function setBackgroundInert(on) {
  for (const sel of BACKGROUND) $(sel).toggleAttribute("inert", on);
}
function drawerFocusables() {
  return [...$("#drawer").querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter((el) => !el.disabled && !el.closest("[hidden]"));
}
// Revision colours: each meeting of a series is a revision issued in its own page colour.
const REV_NAMES = { a: "white", b: "blue", c: "pink", d: "yellow", e: "green", f: "goldenrod" };
const revLetter = (meetingId) => String(meetingId || "").slice(-1);
const revClass = (meetingId) => (REV_NAMES[revLetter(meetingId)] ? `rev-${revLetter(meetingId)}` : "rev-a");

async function openTranscript(meetingId, turnIdx, quote, lead = null) {
  if (!drawerOpen()) lastFocus = document.activeElement;
  const drawer = $("#drawer"), body = $("#drawer-body");
  $("#drawer-title").textContent = `${meetingId} · turn ${turnIdx ?? ""}`;
  body.replaceChildren(h("p", { class: "working" }, "Loading transcript…"));
  setBusy(body, true);
  drawer.setAttribute("aria-hidden", "false");
  $("#scrim").hidden = false;
  setBackgroundInert(true);
  // Focus moves into the dialog at once (the trigger is now inert); the dialog
  // name, meeting and turn, is read on entry. The body is focusable so the
  // transcript can be scrolled from the keyboard.
  body.focus();
  try {
    const start = Math.max(0, (turnIdx ?? 0) - 12);
    const turns = await (await api(`/api/meetings/${encodeURIComponent(meetingId)}/turns?start=${start}&end=${(turnIdx ?? 0) + 25}`)).json();
    body.replaceChildren(...(lead ? [lead] : []), ...turns.map((t) => {
      const isTarget = t.idx === turnIdx;
      return h("div", { class: `turn${isTarget ? " target" : ""}`, id: isTarget ? "target-turn" : null },
        h("div", { class: "who" }, `[${t.idx}] ${t.speaker}`, h("br"), t.time),
        h("div", {}, isTarget && quote ? highlight(t.text, quote) : t.text));
    }));
    const target = $("#target-turn");
    if (target) target.scrollIntoView({ block: "center" });
  } catch (e) {
    body.replaceChildren(h("p", { class: "notice" }, `Could not load transcript: ${e.message}`));
    announce(`Could not load transcript: ${e.message}`, { urgent: true });
  } finally {
    setBusy(body, false);
  }
}
function highlight(text, quote) {
  const i = text.toLowerCase().indexOf(quote.toLowerCase());
  if (i < 0) return text;
  const frag = document.createDocumentFragment();
  frag.append(text.slice(0, i), h("mark", {}, text.slice(i, i + quote.length)), text.slice(i + quote.length));
  return frag;
}
function closeDrawer() {
  if (!drawerOpen()) return;
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
  setBackgroundInert(false);
  // Return focus to the citation that opened the drawer; if it is gone, to the current tab.
  const back = lastFocus && document.contains(lastFocus) ? lastFocus : $('.tabs [aria-selected="true"]');
  lastFocus = null;
  back?.focus();
}
$("#drawer-close").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (!drawerOpen()) return;
  if (e.key === "Escape") { e.preventDefault(); closeDrawer(); return; }
  if (e.key !== "Tab") return;
  // Focus trap: Tab and Shift+Tab cycle inside the dialog.
  const items = drawerFocusables();
  if (!items.length) { e.preventDefault(); return; }
  const first = items[0], last = items.at(-1), active = document.activeElement;
  if (!$("#drawer").contains(active)) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
  else if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
});

function citeButton(c) {
  return h("button", { class: `cite ${revClass(c.meeting_id)}`, type: "button", onclick: () => openTranscript(c.meeting_id, c.turn, c.quote) },
    h("span", { class: "where" }, `${c.meeting_id} · turn ${c.turn} · Speaker ${c.speaker} · ${c.time}${c.method && c.method !== "exact" ? ` · ${c.method}` : ""}`),
    h("q", {}, c.quote));
}
function citeChip(c) {
  return h("button", { class: `chip-cite ${revClass(c.meeting_id)}`, type: "button", title: c.quote, onclick: () => openTranscript(c.meeting_id, c.turn ?? c.turn_idx, c.quote) },
    `${c.meeting_id}·${c.turn ?? c.turn_idx}`);
}

// ---------- Ask ----------
async function loadExamples() {
  try {
    const ex = await (await api("/api/examples")).json();
    const sel = $("#examples");
    const groups = { catalist: "Catalist questions", gold: "Our checked questions" };
    for (const [set, label] of Object.entries(groups)) {
      const g = h("optgroup", { label });
      ex.filter((e) => e.set === set).forEach((e) => g.append(h("option", { value: e.question, "data-team": e.team }, `${e.id} · ${e.question.slice(0, 90)}`)));
      if (g.childElementCount) sel.append(g);
    }
    sel.addEventListener("change", () => {
      const opt = sel.selectedOptions[0];
      if (!opt || !opt.value) return;
      $("#q").value = opt.value;
      $("#ask-team").value = opt.dataset.team || "";
    });
  } catch {}
}

function addTrace(ev) {
  const list = $("#trace");
  list.querySelector(".empty")?.remove();
  list.append(h("li", {},
    h("span", { class: "n" }, ev.step),
    h("span", { class: `k ${ev.kind}` }, ev.kind === "tool_call" || ev.kind === "tool_result" ? ev.name : prettyKind[ev.kind] || ev.kind),
    h("span", { class: "d" }, ev.kind === "tool_result" ? `→ ${ev.detail}` : ev.detail)));
  list.scrollTop = list.scrollHeight;
}

function renderAnswer(r) {
  const a = $("#answer");
  const nodes = [badge(r.state, r.state)];
  if (r.answer) nodes.push(h("p", { class: "text" }, r.answer));
  else nodes.push(h("p", { class: "notice" }, r.error || "No verified answer."));
  if (r.citations?.length) nodes.push(h("h2", { class: "section-title" }, "Evidence"), h("div", { class: "cites" }, r.citations.map(citeButton)));
  if (r.error && r.answer) nodes.push(h("p", { class: "notice" }, r.error));
  const u = r.usage || {};
  nodes.push(h("p", { class: "meta" }, `${r.steps} model steps · ${r.tool_calls} tool calls · ${r.seconds}s · ${(u.input_tokens || 0).toLocaleString()} in / ${(u.output_tokens || 0).toLocaleString()} out tokens · $${(u.cost_usd || 0).toFixed(3)}`));
  a.replaceChildren(...nodes);
}

function clearQuestionError() {
  $("#q-error").hidden = true;
  $("#q").removeAttribute("aria-invalid");
  $("#q").removeAttribute("aria-describedby");
}
$("#q").addEventListener("input", () => { if ($("#q").getAttribute("aria-invalid")) clearQuestionError(); });

// Busy buttons use aria-disabled, not disabled, so keyboard focus stays on them.
function setButtonBusy(btn, busy, label) {
  btn.setAttribute("aria-disabled", String(busy));
  btn.textContent = label;
}
const isBusy = (btn) => btn.getAttribute("aria-disabled") === "true";

$("#ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#ask-btn");
  if (isBusy(btn)) return;
  const q = $("#q").value.trim();
  const err = $("#q-error");
  if (q.length < 5) {
    // Focus moves to the field, which reads its label, invalid state and this description.
    err.textContent = "Write a question of at least a few words."; err.hidden = false;
    $("#q").setAttribute("aria-invalid", "true");
    $("#q").setAttribute("aria-describedby", "q-error");
    $("#q").focus(); return;
  }
  clearQuestionError();
  setButtonBusy(btn, true, "Working…");
  $("#trace").replaceChildren();
  $("#answer").replaceChildren(h("p", { class: "working" }, "Retrieving and verifying. Each step below is a real tool call."));
  setBusy($("#answer"), true);
  announce("Working on your question. Searching transcripts and verifying quotes.");
  let settled = false;
  try {
    const res = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q, team: $("#ask-team").value || null }) });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i); buf = buf.slice(i + 2);
        const ev = /^event: (.*)$/m.exec(block)?.[1];
        const data = /^data: (.*)$/m.exec(block)?.[1];
        if (!ev || !data) continue;
        const payload = JSON.parse(data);
        if (ev === "trace") addTrace(payload);
        else if (ev === "result") { renderAnswer(payload); announceAnswer(payload); settled = true; }
        else if (ev === "error") {
          $("#answer").replaceChildren(badge("failed"), h("p", { class: "notice" }, payload.message));
          announce(`Question failed: ${payload.message}`, { urgent: true }); settled = true;
        }
      }
    }
    if (!settled) announce("The answer stream ended without a result.", { urgent: true });
  } catch (ex) {
    $("#answer").replaceChildren(badge("failed"), h("p", { class: "notice" }, ex.message));
    announce(`Question failed: ${ex.message}`, { urgent: true });
  } finally {
    setBusy($("#answer"), false);
    setButtonBusy(btn, false, "Ask"); loadStatus();
  }
});

// A short outcome line; the answer itself is read when the user moves to it.
function announceAnswer(r) {
  const state = String(r.state || "").replace(/_/g, " ");
  const n = r.citations?.length || 0;
  if (r.answer) announce(`Answer ready, ${state}, ${plural(n, "verified citation")}.`);
  else announce(`No verified answer, ${state}. ${r.error || ""}`.trim(), { urgent: true });
}

// ---------- Memory ----------
let memFilter = "all";
let asOf = null;

// Radio group pattern: one Tab stop (the checked option); arrow keys, Home and
// End move the selection. Focus survives the re-render that follows a pick.
const RADIO_KEYS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1, Home: "first", End: "last" };
function segmented(container, options, current, onPick) {
  const hadFocus = container.contains(document.activeElement);
  const buttons = options.map(([value, label], i) => h("button", {
    type: "button", role: "radio", "aria-checked": String(value === current), tabindex: value === current ? "0" : "-1",
    onclick: () => onPick(value),
    onkeydown: (e) => {
      const k = RADIO_KEYS[e.key];
      if (k === undefined) return;
      e.preventDefault();
      const j = k === "first" ? 0 : k === "last" ? buttons.length - 1 : (i + k + buttons.length) % buttons.length;
      buttons.forEach((b, n) => { b.setAttribute("aria-checked", String(n === j)); b.tabIndex = n === j ? 0 : -1; });
      buttons[j].focus();
      onPick(options[j][0]);
    },
  }, label));
  if (buttons.length && !buttons.some((b) => b.tabIndex === 0)) buttons[0].tabIndex = 0;
  container.replaceChildren(...buttons);
  if (hadFocus) buttons.find((b) => b.tabIndex === 0)?.focus();
}

function threadMatches(t) {
  if (memFilter === "changed") return t.changed;
  if (memFilter === "actions") return t.items.some((i) => i.kind === "action_item" && i.status === "open");
  if (memFilter === "disputes") return t.items.some((i) => ["disagreement", "objection", "question"].includes(i.kind) && i.status === "open");
  return true;
}

let memRequest = 0;
async function loadMemory() {
  const team = $("#mem-team").value;
  if (!team) return;
  const holder = $("#threads");
  const req = ++memRequest; // rapid arrow-key picks: only the latest response renders
  // Scrubbing or filtering the same team keeps the current page mounted (busy) and
  // swaps it when the response lands, so lines re-tint where they sit.
  if (shownTeam !== team || !holder.querySelector(".revision-page")) {
    holder.replaceChildren(h("p", { class: "working" }, "Loading memory…"));
  }
  setBusy(holder, true);
  try {
    const q = asOf ? `?as_of=${asOf}` : "";
    const m = await (await api(`/api/teams/${team}/memory${q}`)).json();
    if (req !== memRequest) return;
    segmented($("#asof"), [[null, "latest"], ...m.meetings.map((x) => [x.ordinal, x.meeting_id.slice(-1)])], asOf, (v) => { asOf = v; loadMemory(); });
    segmented($("#mem-filter"), [["all", "all"], ["changed", "changed"], ["actions", "open actions"], ["disputes", "open disputes"]], memFilter,
      (v) => { memFilter = v; loadMemory(); });
    // Legend built from this team's meetings, so it always matches the row tints exactly.
    $("#rev-legend").replaceChildren(...m.meetings.map((mt) =>
      h("span", { class: `swatch ${revClass(mt.meeting_id)}` }, h("b", {}, revLetter(mt.meeting_id)), REV_NAMES[revLetter(mt.meeting_id)] || "")));
    $("#meetings-strip").replaceChildren(...m.meetings.map((mt) => {
      const roles = m.roles[mt.meeting_id] || {};
      const rtxt = Object.entries(roles).sort().map(([sp, r]) => `${sp} ${r.role.split(" ").map((w) => w[0]).join("")}${r.name ? " " + r.name : ""}`).join(" · ");
      const future = asOf && mt.ordinal > asOf;
      // One complete line per meeting; the full summary is the card's tooltip, never a clipped sentence.
      return h("div", { class: `meeting-card ${future ? "future" : revClass(mt.meeting_id)}`, title: mt.summary || "Not extracted yet." },
        h("h3", {}, mt.meeting_id, h("span", {}, future ? "not yet held" : `${REV_NAMES[revLetter(mt.meeting_id)] || ""} pages`)),
        h("div", { class: "roles" }, `${rtxt || "roles unresolved"} · ${mt.n_turns} turns`));
    }));
    const threads = m.threads.filter(threadMatches);
    const when = asOf ? `as of the end of meeting ${m.meetings.find((x) => x.ordinal === asOf)?.meeting_id ?? asOf}` : "latest state";
    if (!m.threads.length) {
      holder.replaceChildren(h("p", { class: "notice" }, "No extracted memory for this team yet. Run: python -m meeting_memory ingest"));
      announce(`No extracted memory for ${team} yet.`);
      return;
    }
    if (!threads.length) {
      holder.replaceChildren(h("p", { class: "notice" }, "No threads match this filter at this point in time."));
      announce(`${team}, ${when}: no threads match this filter.`);
      return;
    }
    // What changed leads: changed lines first, then open items, then settled ones;
    // newest revision first within each group (the server already orders by recency).
    const rank = (t) => { const k = statusMarks(t); return k.includes("changed") ? 0 : k.includes("open") || k.includes("dispute") ? 1 : k.includes("current") ? 2 : 3; };
    const rows = threads.map((t, i) => [rank(t), i, t]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , t]) => renderRevisionRow(t));
    // Script pages state their revision at the top: colour, meeting, what this revision touched.
    const atMeeting = asOf ? m.meetings.find((x) => x.ordinal === asOf) : m.meetings.at(-1);
    const revId = atMeeting?.meeting_id || "";
    const touched = threads.filter((t) => t.items.at(-1).meeting_id === revId).length;
    const changedHere = threads.filter((t) => t.changed && t.items.at(-1).meeting_id === revId).length;
    shownTeam = team;
    holder.replaceChildren(h("div", { class: "revision-page" },
      h("p", { class: `rev-head ${revClass(revId)}` },
        h("b", {}, `${(REV_NAMES[revLetter(revId)] || "").toUpperCase()} REVISION · ${revId}`),
        h("span", { class: "long" }, `${plural(touched, "line")} revised in this meeting, ${changedHere} of them changed earlier decisions · ${plural(threads.length, "line")} shown`),
        h("span", { class: "short", "aria-hidden": "true" }, `${touched} revised · ${changedHere} changed`)),
      h("div", { class: `slug ${revClass(revId)}`, "aria-hidden": "true" }, h("span", {}, "Topic"), h("span", {}, "Current line"), h("span", {}, "Last revised"), h("span", {}, "Status")),
      h("ol", { class: "rev-list", "aria-label": `${team} decision threads, ${when}` }, rows.map((r) => h("li", {}, r)))));
    lastTint = nextTint;
    nextTint = new Map();
    announce(`${team}, ${when}: ${plural(threads.length, "thread")} shown.`);
  } catch (e) {
    if (req !== memRequest) return;
    holder.replaceChildren(h("p", { class: "notice" }, `Could not load memory: ${e.message}`));
    announce(`Could not load memory: ${e.message}`, { urgent: true });
  } finally {
    if (req === memRequest) setBusy(holder, false);
  }
}

// The tint each row had at the previous render, so a scrub of "Revision as of"
// can animate a line from its old revision colour to its new one.
let lastTint = new Map();
let nextTint = new Map();
let shownTeam = null;
const GONE = ["superseded", "cancelled", "rejected"];
const MARKS = {
  changed: ["Changed", "An earlier decision on this topic was replaced or dropped in a later meeting."],
  open: ["Open action", "Someone committed to do this and no later meeting records it done."],
  dispute: ["Open dispute", "A disagreement, objection or question that no later meeting settled."],
  current: ["Current", "Decided, and not changed since."],
  noted: ["Noted", "Recorded in the meetings; no decision on it yet."],
};

function statusMarks(t) {
  const has = (kinds, status = "open") => t.items.some((i) => kinds.includes(i.kind) && i.status === status);
  const keys = [];
  if (t.changed) keys.push("changed");
  if (has(["action_item"])) keys.push("open");
  if (has(["disagreement", "objection", "question"])) keys.push("dispute");
  if (!keys.length) keys.push(t.current.length ? "current" : "noted");
  return keys;
}

function threadHistory(t) {
  return h("div", {},
    h("p", { class: "history-title" }, `${t.topic}: every revision`),
    h("ol", { class: "history" }, t.items.map((i) => h("li", { class: revClass(i.meeting_id) },
      h("span", { class: "mid" }, i.meeting_id),
      h("span", {}, GONE.includes(i.status) ? h("s", {}, i.statement) : i.statement, ` (${i.kind.replace("_", " ")}, ${i.status})`)))));
}

function renderRevisionRow(t) {
  const current = t.items.filter((i) => t.current.includes(i.item_id));
  const latest = t.items.at(-1);
  const lead = current.at(-1) || latest;
  const was = t.items.filter((i) => ["decision", "proposal"].includes(i.kind) && GONE.includes(i.status)).reverse().slice(0, 2);
  const ev = (lead.evidence && lead.evidence[0]) || t.items.flatMap((i) => i.evidence || []).at(-1);
  const tint = revClass(latest.meeting_id);
  const prev = lastTint.get(t.thread_id);
  nextTint.set(t.thread_id, tint);
  const marks = statusMarks(t);
  const row = h("button", {
    type: "button", class: `rev-row ${tint}${prev && prev !== tint ? " retint" : ""}`,
    style: prev && prev !== tint ? `--from: var(--${prev})` : null,
    disabled: ev ? null : true,
    onclick: ev ? () => openTranscript(ev.meeting_id, ev.turn_idx, ev.quote, threadHistory(t)) : null,
  },
    h("span", { class: "topic" }, t.topic),
    h("span", {},
      h("span", { class: "line" }, current.length ? current.map((i) => i.statement).join(" ") : lead.statement),
      was.length ? h("ul", { class: "was" }, was.map((i) => h("li", {},
        h("b", { class: `rev-chip ${revClass(i.meeting_id)}` }, `Was, ${revLetter(i.meeting_id)} ${REV_NAMES[revLetter(i.meeting_id)] || ""}`), " ",
        h("s", {}, i.statement)))) : null),
    h("span", { class: "when" }, latest.meeting_id, ev ? h("small", {}, `turn ${ev.turn_idx}`) : null),
    h("span", { class: "marks" }, marks.map((k) => h("span", { class: `mark-label ${k}`, title: MARKS[k][1] }, MARKS[k][0]))));
  return row;
}

// ---------- Brief ----------
function fillMeetings(team) {
  const t = TEAMS.find((x) => x.team === team);
  const sel = $("#brief-before");
  sel.replaceChildren(...(t?.meetings || []).slice(1).map((m) => h("option", { value: m }, m)));
  sel.value = t?.meetings.at(-1) || "";
}

$("#brief-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#brief-btn"), out = $("#brief");
  if (isBusy(btn)) return;
  setButtonBusy(btn, true, "Writing…");
  out.replaceChildren(h("p", { class: "working" }, $("#brief-llm").checked ? "Selecting facts from memory, then writing prose with the model…" : "Selecting facts from memory…"));
  setBusy(out, true);
  announce(`Writing the brief for ${$("#brief-before").value || "the next meeting"}.`);
  try {
    const b = await (await api("/api/brief", { method: "POST", body: JSON.stringify({ team: $("#brief-team").value, before: $("#brief-before").value || null, use_llm: $("#brief-llm").checked }) })).json();
    const titles = { decided: "What has been decided", changed: "What changed along the way", open_actions: "Open actions and owners", open_disagreements: "Disagreements and questions still open" };
    const copy = h("button", { class: "ghost", type: "button", onclick: async () => {
      try { await navigator.clipboard.writeText(b.text); copy.textContent = "Copied"; announce("Brief copied to the clipboard."); }
      catch (err) { announce(`Could not copy: ${err.message}`, { urgent: true }); }
    } }, "Copy as text");
    out.replaceChildren(
      h("h2", {}, `Before ${b.before_meeting}`),
      h("p", { class: "basis" }, `Based on ${b.based_on.join(", ")} · ${b.mode === "llm" ? "prose by model, facts and quotes by code" : "deterministic"}${b.dropped_points ? ` · ${b.dropped_points} uncited point(s) dropped` : ""}`),
      b.note ? h("p", { class: "notice" }, b.note) : null,
      ...Object.entries(titles).flatMap(([k, title]) => [
        h("h3", {}, title),
        b.sections[k]?.length ? h("ul", {}, b.sections[k].map((p) => h("li", {}, p.text, ...p.citations.map(citeChip)))) : h("p", { class: "by" }, "Nothing recorded."),
      ]),
      h("p", {}, copy),
    );
    const points = Object.keys(titles).reduce((n, k) => n + (b.sections[k]?.length || 0), 0);
    announce(`Brief ready for ${b.before_meeting}: ${plural(points, "cited point")}.`);
  } catch (ex) {
    out.replaceChildren(h("p", { class: "notice" }, `Could not write the brief: ${ex.message}`));
    announce(`Could not write the brief: ${ex.message}`, { urgent: true });
  } finally { setBusy(out, false); setButtonBusy(btn, false, "Write brief"); }
});

// ---------- Boot ----------
(async function boot() {
  loadStatus();
  loadExamples();
  try {
    TEAMS = await (await api("/api/teams")).json();
    for (const id of ["#ask-team", "#mem-team", "#brief-team"]) {
      const sel = $(id);
      TEAMS.forEach((t) => sel.append(h("option", { value: t.team }, `${t.team}${t.extracted < t.meetings.length ? " (not extracted)" : ""}`)));
    }
    $("#mem-team").value = "TS3012"; $("#brief-team").value = "TS3012";
    fillMeetings("TS3012");
    $("#mem-team").addEventListener("change", () => { asOf = null; loadMemory(); });
    $("#brief-team").addEventListener("change", (e) => fillMeetings(e.target.value));
  } catch (e) {
    $("#status").textContent = `Server unreachable: ${e.message}`;
    announce(`Server unreachable: ${e.message}`, { urgent: true });
  }
  const initial = location.hash.slice(1);
  selectTab(tabs.includes(initial) ? initial : "ask");
  window.addEventListener("hashchange", () => {
    const t = location.hash.slice(1);
    if (tabs.includes(t)) selectTab(t);
  });
})();
