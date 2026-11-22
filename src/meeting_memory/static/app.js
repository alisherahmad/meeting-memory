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
  } catch (e) { $("#status").textContent = `Status unavailable: ${e.message}`; }
}

// ---------- Transcript drawer ----------
let lastFocus = null;
async function openTranscript(meetingId, turnIdx, quote) {
  lastFocus = document.activeElement;
  const drawer = $("#drawer"), body = $("#drawer-body");
  $("#drawer-title").textContent = `${meetingId} · turn ${turnIdx ?? ""}`;
  body.replaceChildren(h("p", { class: "working" }, "Loading transcript…"));
  drawer.setAttribute("aria-hidden", "false");
  $("#scrim").hidden = false;
  try {
    const start = Math.max(0, (turnIdx ?? 0) - 12);
    const turns = await (await api(`/api/meetings/${encodeURIComponent(meetingId)}/turns?start=${start}&end=${(turnIdx ?? 0) + 25}`)).json();
    body.replaceChildren(...turns.map((t) => {
      const isTarget = t.idx === turnIdx;
      return h("div", { class: `turn${isTarget ? " target" : ""}`, id: isTarget ? "target-turn" : null },
        h("div", { class: "who" }, `[${t.idx}] ${t.speaker}`, h("br"), t.time),
        h("div", {}, isTarget && quote ? highlight(t.text, quote) : t.text));
    }));
    const target = $("#target-turn");
    if (target) target.scrollIntoView({ block: "center" });
  } catch (e) {
    body.replaceChildren(h("p", { class: "notice" }, `Could not load transcript: ${e.message}`));
  }
  body.focus();
}
function highlight(text, quote) {
  const i = text.toLowerCase().indexOf(quote.toLowerCase());
  if (i < 0) return text;
  const frag = document.createDocumentFragment();
  frag.append(text.slice(0, i), h("mark", {}, text.slice(i, i + quote.length)), text.slice(i + quote.length));
  return frag;
}
function closeDrawer() {
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
  if (lastFocus) lastFocus.focus();
}
$("#drawer-close").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#drawer").getAttribute("aria-hidden") === "false") closeDrawer(); });

function citeButton(c) {
  return h("button", { class: "cite", type: "button", onclick: () => openTranscript(c.meeting_id, c.turn, c.quote) },
    h("span", { class: "where" }, `${c.meeting_id} · turn ${c.turn} · Speaker ${c.speaker} · ${c.time}${c.method && c.method !== "exact" ? ` · ${c.method}` : ""}`),
    h("q", {}, c.quote));
}
function citeChip(c) {
  return h("button", { class: "chip-cite", type: "button", title: c.quote, onclick: () => openTranscript(c.meeting_id, c.turn ?? c.turn_idx, c.quote) },
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

$("#ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  const err = $("#q-error");
  if (q.length < 5) {
    err.textContent = "Write a question of at least a few words."; err.hidden = false;
    $("#q").setAttribute("aria-invalid", "true"); $("#q").focus(); return;
  }
  err.hidden = true; $("#q").removeAttribute("aria-invalid");
  const btn = $("#ask-btn");
  btn.disabled = true; btn.textContent = "Working…";
  $("#trace").replaceChildren();
  $("#answer").replaceChildren(h("p", { class: "working" }, "Retrieving and verifying. Each step below is a real tool call."));
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
        else if (ev === "result") renderAnswer(payload);
        else if (ev === "error") $("#answer").replaceChildren(badge("failed"), h("p", { class: "notice" }, payload.message));
      }
    }
  } catch (ex) {
    $("#answer").replaceChildren(badge("failed"), h("p", { class: "notice" }, ex.message));
  } finally {
    btn.disabled = false; btn.textContent = "Ask"; loadStatus();
  }
});

// ---------- Memory ----------
let memFilter = "all";
let asOf = null;

function segmented(container, options, current, onPick) {
  container.replaceChildren(...options.map(([value, label]) => h("button", {
    type: "button", role: "radio", "aria-checked": String(value === current),
    onclick: () => onPick(value),
  }, label)));
}

function threadMatches(t) {
  if (memFilter === "changed") return t.changed;
  if (memFilter === "actions") return t.items.some((i) => i.kind === "action_item" && i.status === "open");
  if (memFilter === "disputes") return t.items.some((i) => ["disagreement", "objection", "question"].includes(i.kind) && i.status === "open");
  return true;
}

async function loadMemory() {
  const team = $("#mem-team").value;
  if (!team) return;
  const holder = $("#threads");
  holder.replaceChildren(h("p", { class: "working" }, "Loading memory…"));
  try {
    const q = asOf ? `?as_of=${asOf}` : "";
    const m = await (await api(`/api/teams/${team}/memory${q}`)).json();
    segmented($("#asof"), [[null, "latest"], ...m.meetings.map((x) => [x.ordinal, x.meeting_id.slice(-1)])], asOf, (v) => { asOf = v; loadMemory(); });
    segmented($("#mem-filter"), [["all", "all"], ["changed", "changed"], ["actions", "open actions"], ["disputes", "open disputes"]], memFilter,
      (v) => { memFilter = v; loadMemory(); });
    $("#meetings-strip").replaceChildren(...m.meetings.map((mt) => {
      const roles = m.roles[mt.meeting_id] || {};
      const rtxt = Object.entries(roles).sort().map(([sp, r]) => `${sp} ${r.role.split(" ").map((w) => w[0]).join("")}${r.name ? " " + r.name : ""}`).join(" · ");
      return h("div", { class: `meeting-card${asOf && mt.ordinal > asOf ? " future" : ""}` },
        h("h3", {}, mt.meeting_id), h("div", { class: "roles" }, rtxt || "roles unresolved"), mt.summary || "Not extracted yet.");
    }));
    const threads = m.threads.filter(threadMatches);
    if (!m.threads.length) {
      holder.replaceChildren(h("p", { class: "notice" }, "No extracted memory for this team yet. Run: python -m meeting_memory ingest"));
      return;
    }
    if (!threads.length) { holder.replaceChildren(h("p", { class: "notice" }, "No threads match this filter at this point in time.")); return; }
    holder.replaceChildren(...threads.map(renderThread));
  } catch (e) {
    holder.replaceChildren(h("p", { class: "notice" }, `Could not load memory: ${e.message}`));
  }
}

function renderThread(t) {
  const current = t.items.filter((i) => t.current.includes(i.item_id));
  const openActions = t.items.filter((i) => i.kind === "action_item" && i.status === "open").length;
  const flags = [];
  if (t.changed) flags.push(badge("changed", "superseded"));
  if (openActions) flags.push(badge(`${openActions} open action${openActions > 1 ? "s" : ""}`, "open"));
  const now = current.length ? `Now: ${current.map((i) => i.statement).join(" / ")}` : `${t.items.length} item${t.items.length > 1 ? "s" : ""}`;
  return h("details", { class: "thread" },
    h("summary", {}, h("div", {}, h("div", { class: "topic" }, t.topic), h("div", { class: "now" }, now)), h("div", { class: "flags" }, flags)),
    h("ol", { class: "timeline" }, t.items.map((i) => h("li", {},
      h("div", { class: "mid" }, i.meeting_id),
      h("div", {},
        h("div", {}, badge(i.kind.replace("_", " "), "kind"), " ", badge(i.status, i.status), i.inferred ? h("span", { class: "by" }, " inferred") : null),
        h("p", { class: `stmt${["superseded", "cancelled", "rejected"].includes(i.status) ? " struck" : ""}` }, i.statement,
          ...(i.evidence || []).slice(0, 2).map((ev) => citeChip({ ...ev, turn: ev.turn_idx }))),
        i.status_by?.length ? h("div", { class: "by" }, `${i.status} by ${i.status_by.join(", ")}`) : null,
      )))));
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
  btn.disabled = true; btn.textContent = "Writing…";
  out.replaceChildren(h("p", { class: "working" }, $("#brief-llm").checked ? "Selecting facts from memory, then writing prose with the model…" : "Selecting facts from memory…"));
  try {
    const b = await (await api("/api/brief", { method: "POST", body: JSON.stringify({ team: $("#brief-team").value, before: $("#brief-before").value || null, use_llm: $("#brief-llm").checked }) })).json();
    const titles = { decided: "What has been decided", changed: "What changed along the way", open_actions: "Open actions and owners", open_disagreements: "Disagreements and questions still open" };
    const copy = h("button", { class: "ghost", type: "button", onclick: async () => { await navigator.clipboard.writeText(b.text); copy.textContent = "Copied"; } }, "Copy as text");
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
  } catch (ex) {
    out.replaceChildren(h("p", { class: "notice" }, `Could not write the brief: ${ex.message}`));
  } finally { btn.disabled = false; btn.textContent = "Write brief"; }
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
  } catch (e) { $("#status").textContent = `Server unreachable: ${e.message}`; }
  const initial = location.hash.slice(1);
  selectTab(tabs.includes(initial) ? initial : "ask");
})();
