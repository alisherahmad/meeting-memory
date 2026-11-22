"""The agent's tool surface: read-only views of the memory store plus one
terminal `submit_answer`. Arguments are validated by pydantic; results are
compact text so the context grows slowly. Nothing here can write to the store,
reach the network or touch the filesystem: least privilege by construction.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from .memory import compute_state, thread_to_dict
from .quotes import MIN_QUOTE_WORDS, resolve_quote, trim_quote
from .retrieval import Retriever
from .roles import merge_roles
from .store import Store

MAX_READ_TURNS = 40
TURN_CHARS_IN_SEARCH = 450


class ToolArgError(ValueError):
    pass


# ---- argument models ---------------------------------------------------------
class ListMeetingsArgs(BaseModel):
    team: str = Field(pattern=r"^[A-Z]{2}\d{4}$")


class SearchMemoryArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    team: str | None = Field(default=None, pattern=r"^[A-Z]{2}\d{4}$")
    kinds: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=20)


class GetThreadArgs(BaseModel):
    thread_id: str = Field(min_length=3, max_length=40)


class SearchTranscriptsArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    team: str | None = Field(default=None, pattern=r"^[A-Z]{2}\d{4}$")
    meeting_id: str | None = Field(default=None, pattern=r"^[A-Z]{2}\d{4}[a-z]$")
    limit: int = Field(default=5, ge=1, le=8)


class ReadTurnsArgs(BaseModel):
    meeting_id: str = Field(pattern=r"^[A-Z]{2}\d{4}[a-z]$")
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @field_validator("end")
    @classmethod
    def _range(cls, v: int, info) -> int:
        start = info.data.get("start", 0)
        if v < start:
            raise ValueError("end must be >= start")
        return min(v, start + MAX_READ_TURNS - 1)


class Citation(BaseModel):
    meeting_id: str = Field(pattern=r"^[A-Z]{2}\d{4}[a-z]$")
    turn: int | None = Field(default=None, ge=0)
    quote: str = Field(min_length=1, max_length=1200)


class SubmitAnswerArgs(BaseModel):
    answer: str = Field(min_length=1, max_length=1200)
    citations: list[Citation] = Field(min_length=1, max_length=3)


# ---- tool definitions sent to the model --------------------------------------
TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "list_meetings",
        "description": "List a team's meetings in time order with each meeting's short summary and the speaker roles resolved FOR THAT MEETING (letters can change between meetings).",
        "input_schema": {"type": "object", "properties": {"team": {"type": "string", "description": "Team id, e.g. TS3012"}},
                         "required": ["team"], "additionalProperties": False},
    },
    {
        "name": "search_memory",
        "description": "Search the extracted memory (decisions, proposals, objections, action items, figures, requirements, questions, reports, disagreements). Each hit shows its thread and its status computed over time (e.g. current / superseded / cancelled / open / done) plus verified evidence quotes. Memory is a pre-digested index and can be incomplete: confirm important details in the transcript.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "team": {"type": "string", "description": "Restrict to one team (recommended)."},
                "kinds": {"type": "array", "items": {"type": "string", "enum": ["decision", "proposal", "objection", "action_item", "figure", "requirement", "question", "report", "disagreement"]}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"], "additionalProperties": False,
        },
    },
    {
        "name": "get_thread",
        "description": "Full chronology of one memory thread (one topic across meetings), oldest first, with what replaced what.",
        "input_schema": {"type": "object", "properties": {"thread_id": {"type": "string"}}, "required": ["thread_id"], "additionalProperties": False},
    },
    {
        "name": "search_transcripts",
        "description": "Hybrid keyword + semantic search over raw transcript passages. Returns passages as numbered turns '[n] X: text'. Use to verify memory, find exact words for citations, or find things memory missed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "team": {"type": "string"},
                "meeting_id": {"type": "string", "description": "Restrict to one meeting, e.g. TS3012c"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query"], "additionalProperties": False,
        },
    },
    {
        "name": "read_turns",
        "description": f"Read consecutive turns of one meeting verbatim (at most {MAX_READ_TURNS} turns per call).",
        "input_schema": {"type": "object", "properties": {"meeting_id": {"type": "string"}, "start": {"type": "integer", "minimum": 0}, "end": {"type": "integer", "minimum": 0}},
                         "required": ["meeting_id", "start", "end"], "additionalProperties": False},
    },
    {
        "name": "submit_answer",
        "description": f"Submit the final answer. 1-3 citations; each quote must be at least {MIN_QUOTE_WORDS} words copied exactly from ONE turn of the cited meeting (give the turn number). Quotes are checked by code; if any fail you will be told which.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "description": "One to three plain sentences."},
                "citations": {
                    "type": "array", "description": "1 to 3 citations (enforced by code; strict schemas cannot express array bounds)",
                    "items": {"type": "object", "properties": {"meeting_id": {"type": "string"}, "turn": {"type": "integer"}, "quote": {"type": "string"}},
                              "required": ["meeting_id", "turn", "quote"], "additionalProperties": False},
                },
            },
            "required": ["answer", "citations"], "additionalProperties": False,
        },
    },
]


def _parse(model: type[BaseModel], args: dict) -> BaseModel:
    try:
        return model.model_validate(args)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        raise ToolArgError(f"Invalid arguments: {problems}") from e


class ToolBox:
    def __init__(self, store: Store, retriever: Retriever, scope_team: str | None = None):
        self.store = store
        self.retriever = retriever
        self.scope_team = scope_team  # if set, citations must come from this team
        self._state_cache: dict[str, dict] = {}

    # -- helpers -------------------------------------------------------------------
    def _state(self, team: str) -> dict:
        if team not in self._state_cache:
            self._state_cache[team] = compute_state(self.store.items(team))
        return self._state_cache[team]

    def _status_of(self, item: dict) -> tuple[str, list[str]]:
        ts = self._state(item["team"]).get(item["thread_id"])
        if ts:
            for s in ts.items:
                if s.item["item_id"] == item["item_id"]:
                    return s.status + (" (inferred)" if s.inferred else ""), s.by
        return "unknown", []

    @staticmethod
    def _fmt_evidence(ev: list[dict]) -> str:
        return " | ".join(f'{e["meeting_id"]}[{e["turn_idx"]}] {e["speaker"]}: "{e["quote"]}"' for e in ev[:2]) or "(no verified quote)"

    # -- tools ---------------------------------------------------------------------
    def list_meetings(self, a: ListMeetingsArgs) -> str:
        rows = self.store.meetings(a.team)
        if not rows:
            return f"No meetings found for team {a.team}."
        roles = merge_roles([dict(r) for r in self.store.roles(a.team)])
        out = []
        for r in rows:
            rl = roles.get(r["meeting_id"], {})
            role_txt = ", ".join(f"{sp}={v['role']}" + (f" ({v['name']})" if v.get("name") else "") for sp, v in sorted(rl.items())) or "roles not resolved"
            out.append(f"{r['meeting_id']} (meeting {r['ordinal']}, {r['n_turns']} turns) roles: {role_txt}\n  summary: {r['summary'] or '(not extracted)'}")
        return "\n".join(out)

    def search_memory(self, a: SearchMemoryArgs) -> str:
        team = a.team or self.scope_team
        ids = self.retriever.search_items(a.query, team=team, kinds=a.kinds, limit=a.limit)
        if not ids:
            return "No memory items matched. Try other words or search_transcripts."
        lines = []
        for iid in ids:
            it = self.store.item(iid)
            if not it:
                continue
            status, by = self._status_of(it)
            meta = f"{it['kind']}, {status}" + (f" by {','.join(by)}" if by else "")
            who = f" speakers={','.join(it['speakers'])}" if it["speakers"] else ""
            who += f" owner={it['owner']}" if it["owner"] else ""
            who += f" value={it['value']}" if it["value"] else ""
            lines.append(f"{iid} [{meta}] thread={it['thread_id']} ({it['topic']}){who}\n  {it['statement']}\n  evidence: {self._fmt_evidence(it['evidence'])}")
        return "\n".join(lines)

    def get_thread(self, a: GetThreadArgs) -> str:
        rows = self.store.query("SELECT team FROM threads WHERE thread_id=?", (a.thread_id,))
        if not rows:
            return f"Unknown thread {a.thread_id}."
        ts = self._state(rows[0]["team"]).get(a.thread_id)
        if not ts:
            return f"Thread {a.thread_id} has no items."
        d = thread_to_dict(ts)
        lines = [f"THREAD {d['thread_id']} — {d['topic']} (current decision items: {', '.join(d['current']) or 'none'})"]
        for it in d["items"]:
            rel = f" {it['relation']}->{','.join(it['related'])}" if it["related"] else (f" {it['relation']}" if it["relation"] != "new" else "")
            st = it["status"] + (" (inferred)" if it["inferred"] else "") + (f" by {','.join(it['status_by'])}" if it["status_by"] else "")
            lines.append(f"{it['item_id']} [{it['kind']}, {st}{rel}] {it['statement']}\n  evidence: {self._fmt_evidence(it['evidence'])}")
        return "\n".join(lines)

    def search_transcripts(self, a: SearchTranscriptsArgs) -> str:
        team = a.team or (a.meeting_id[:-1] if a.meeting_id else None) or self.scope_team
        hits = self.retriever.search_chunks(a.query, team=team, meeting_ids=[a.meeting_id] if a.meeting_id else None, limit=a.limit)
        if not hits:
            return "No passages matched."
        out = []
        for h in hits:
            body = "\n".join(
                (ln if len(ln) <= TURN_CHARS_IN_SEARCH else ln[:TURN_CHARS_IN_SEARCH] + " …") for ln in h.text.split("\n")
            )
            out.append(f"== {h.meeting_id} turns {h.start_idx}-{h.end_idx} ==\n{body}")
        return "\n".join(out)

    def read_turns(self, a: ReadTurnsArgs) -> str:
        turns = self.store.turns(a.meeting_id, a.start, a.end)
        if not turns:
            return f"No turns {a.start}-{a.end} in {a.meeting_id}."
        return "\n".join(f"[{t.idx}] {t.start_time} {t.speaker}: {t.text}" for t in turns)

    def verify_submission(self, a: SubmitAnswerArgs) -> tuple[list[dict], list[str]]:
        """Returns (verified citations, problems). Verified quotes are exact transcript substrings."""
        ok, problems = [], []
        for i, c in enumerate(a.citations, 1):
            if self.scope_team and not c.meeting_id.startswith(self.scope_team):
                problems.append(f"citation {i}: {c.meeting_id} is not a meeting of team {self.scope_team}")
                continue
            turns = self.store.turns(c.meeting_id)
            if not turns:
                problems.append(f"citation {i}: unknown meeting {c.meeting_id}")
                continue
            rq = resolve_quote(turns, c.quote, c.turn)
            if not rq:
                problems.append(f"citation {i}: quote not found verbatim in any single turn of {c.meeting_id} (need >= {MIN_QUOTE_WORDS} exact words)")
                continue
            t = turns[rq.turn_idx]
            ok.append({"meeting_id": c.meeting_id, "quote": trim_quote(rq.quote), "turn": rq.turn_idx, "speaker": t.speaker,
                       "time": t.start_time, "method": rq.method})
        # Same quote twice adds nothing.
        seen, unique = set(), []
        for c in ok:
            key = (c["meeting_id"], c["quote"].lower())
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique, problems

    def dispatch(self, name: str, args: dict) -> str:
        table = {
            "list_meetings": (ListMeetingsArgs, self.list_meetings),
            "search_memory": (SearchMemoryArgs, self.search_memory),
            "get_thread": (GetThreadArgs, self.get_thread),
            "search_transcripts": (SearchTranscriptsArgs, self.search_transcripts),
            "read_turns": (ReadTurnsArgs, self.read_turns),
        }
        if name not in table:
            raise ToolArgError(f"Unknown tool {name!r}")
        model, fn = table[name]
        return fn(_parse(model, args))


def args_key(name: str, args: dict) -> str:
    return name + ":" + json.dumps(args, sort_keys=True)
