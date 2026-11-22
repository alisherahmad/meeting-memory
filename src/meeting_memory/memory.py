"""Time-aware memory state. Pure code: no LLM.

The extraction model labels each new item with a thread (topic) and a relation to
earlier items ("replaces", "fulfils", ...). This module turns those labels into
state, using meeting order as the clock:

* an item can only affect items from *earlier* meetings (or earlier in the same
  meeting) - links pointing forward in time are discarded at ingest;
* a decision is CURRENT until a later item replaces or cancels it;
* an action item is OPEN until a later item fulfils it;
* a disagreement / question is OPEN until a later item resolves / answers it, or
  a later decision lands in the same thread (marked as inferred);
* a proposal is OPEN until adopted (a later decision links to it) or rejected.

`as_of_ordinal` replays history: state "before meeting d" is computed from items
in meetings a-c only, which is what a pre-meeting brief needs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

KINDS = ("decision", "proposal", "objection", "action_item", "figure", "requirement", "question", "disagreement", "report")
RELATIONS = ("new", "replaces", "cancels", "confirms", "refines", "adopts", "rejects", "fulfils", "resolves", "answers", "reopens")


@dataclass
class ItemState:
    item: dict
    status: str
    by: list[str] = field(default_factory=list)  # item ids that caused the status
    inferred: bool = False


@dataclass
class ThreadState:
    thread_id: str
    topic: str
    items: list[ItemState]

    @property
    def current_decisions(self) -> list[ItemState]:
        return [s for s in self.items if s.item["kind"] == "decision" and s.status in ("current", "reopened")]

    @property
    def changed(self) -> bool:
        return any(s.status in ("superseded", "cancelled") for s in self.items if s.item["kind"] == "decision")

    def open_of(self, kind: str) -> list[ItemState]:
        return [s for s in self.items if s.item["kind"] == kind and s.status == "open"]


def _order(it: dict) -> tuple[int, int]:
    return (it["ordinal"], it["seq"])


def compute_state(items: list[dict], as_of_ordinal: int | None = None) -> dict[str, ThreadState]:
    """items: dicts from Store.items(); returns {thread_id: ThreadState}."""
    if as_of_ordinal is not None:
        items = [i for i in items if i["ordinal"] <= as_of_ordinal]
    items = sorted(items, key=_order)
    by_id = {i["item_id"]: i for i in items}
    status: dict[str, ItemState] = {}
    for it in items:
        initial = {
            "decision": "current", "action_item": "open", "disagreement": "open", "question": "open", "proposal": "open",
            "objection": "open",
        }.get(it["kind"], "noted")
        status[it["item_id"]] = ItemState(it, initial)

    by_thread: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_thread[it["thread_id"]].append(it)

    for it in items:
        rel = it["relation"]
        targets = [by_id[r] for r in it["related"] if r in by_id and _order(by_id[r]) < _order(it)]
        tid = it["thread_id"]
        if rel in ("replaces", "cancels") and it["kind"] == "decision" and not targets:
            # Implicit target: whatever decision was current in this thread.
            targets = [p for p in by_thread[tid] if _order(p) < _order(it) and p["kind"] == "decision"
                       and status[p["item_id"]].status in ("current", "reopened")]
        for t in targets:
            st = status[t["item_id"]]
            new = None
            if rel == "replaces" and t["kind"] in ("decision", "proposal", "requirement"):
                new = "superseded"
            elif rel == "cancels":
                new = "cancelled"
            elif rel in ("adopts", "confirms", "refines") and t["kind"] == "proposal":
                new = "adopted"
            elif rel == "refines" and t["kind"] == "decision":
                new = "refined"
            elif rel == "rejects" and t["kind"] in ("proposal", "objection", "decision"):
                new = "rejected" if t["kind"] != "decision" else "cancelled"
            elif rel == "fulfils" and t["kind"] == "action_item":
                new = "done"
            elif rel == "resolves" and t["kind"] in ("disagreement", "objection", "question"):
                new = "resolved"
            elif rel == "answers" and t["kind"] in ("question", "action_item"):
                new = "answered" if t["kind"] == "question" else "done"
            elif rel == "reopens" and t["kind"] == "decision":
                # A later *decision* that reopens an earlier one settles it differently;
                # a question or objection only puts it back in play.
                new = "superseded" if it["kind"] == "decision" else "reopened"
            if new:
                st.status, st.by = new, st.by + [it["item_id"]]

        # Inferred resolution: a later decision in the same thread closes open
        # disagreements/objections there. Marked inferred so it is never presented
        # as something the team said explicitly.
        if it["kind"] == "decision":
            for p in by_thread[tid]:
                if _order(p) < _order(it) and p["kind"] in ("disagreement", "objection"):
                    ps = status[p["item_id"]]
                    if ps.status == "open":
                        ps.status, ps.by, ps.inferred = "resolved", [it["item_id"]], True

    threads: dict[str, ThreadState] = {}
    for tid, its in by_thread.items():
        topic = its[0]["topic"]  # the topic the thread was created with; later items don't relabel it
        threads[tid] = ThreadState(tid, topic, [status[i["item_id"]] for i in its])
    return threads


def last_activity(ts: ThreadState) -> tuple[int, int]:
    return max(_order(s.item) for s in ts.items)


def render_prior_state(threads: dict[str, ThreadState], max_threads: int = 60, max_items_per_thread: int = 6) -> str:
    """Compact text of a team's memory, fed to the extractor for the next meeting so
    it can link back-references ("like we said last time") to existing items."""
    if not threads:
        return "(no earlier meetings for this team)"
    lines = []
    ordered = sorted(threads.values(), key=last_activity, reverse=True)[:max_threads]
    for ts in ordered:
        lines.append(f"THREAD {ts.thread_id} — {ts.topic}")
        shown = ts.items[-max_items_per_thread:]
        for s in shown:
            it = s.item
            extra = f" owner={it['owner']}" if it["owner"] else ""
            extra += f" value={it['value']}" if it["value"] else ""
            lines.append(f"  {it['item_id']} [{it['kind']}, {s.status}{extra}] {it['statement']}")
    return "\n".join(lines)


def thread_to_dict(ts: ThreadState) -> dict:
    return {
        "thread_id": ts.thread_id,
        "topic": ts.topic,
        "changed": ts.changed,
        "current": [s.item["item_id"] for s in ts.current_decisions],
        "items": [
            {
                "item_id": s.item["item_id"], "meeting_id": s.item["meeting_id"], "kind": s.item["kind"],
                "relation": s.item["relation"], "related": s.item["related"], "status": s.status, "status_by": s.by,
                "inferred": s.inferred, "statement": s.item["statement"], "speakers": s.item["speakers"],
                "owner": s.item["owner"], "value": s.item["value"], "evidence": s.item["evidence"],
                "verified": s.item["verified"],
            }
            for s in ts.items
        ],
    }
