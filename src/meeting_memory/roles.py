"""Speaker-role resolution.

Letters are NOT stable identities across a team's meetings (e.g. in IS1000 the
letters C and D swap between meetings c and d), so roles are resolved *per
meeting*:

1. Deterministic: self-introductions matched by regex ("I'm the Project Manager",
   "my role is ... industrial designer"). High precision, mostly meeting a.
2. Model: the per-meeting extraction also proposes roles with an evidence quote
   (names, "as marketing expert I looked at...", who presents what). Each one is
   kept only if its quote verifies against a turn spoken by that speaker.

Merging prefers the regex source when they conflict.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .transcripts import Meeting

ROLES = ("Project Manager", "Industrial Designer", "User Interface Designer", "Marketing Expert")

_ROLE_PATTERNS = {
    "Project Manager": r"project\s+manager|project\s+leader",
    "Industrial Designer": r"industrial\s+design(?:er)?",
    "User Interface Designer": r"user\s+interface(?:\s+design(?:er)?)?|interface\s+designer|u\s*_?\s*i\s+designer",
    "Marketing Expert": r"marketing(?:\s+(?:expert|person|manager|executive|department|guy))?",
}
_SELF = r"(?:i\s*'?\s*a?m|i\s+am|i\s*'?ll\s+be|i\s+will\s+be|my\s+(?:role|job|position|function)\s+(?:is|will\s+be)|i\s+work\s+as|i\s*'?\s*m\s+working\s+as|i\s+play)"
_FILLER = r"(?:\s+(?:um|uh|the|a|an|your|our|going\s+to\s+be|gonna\s+be|be|as|here|just|today|for\s+today|uh,|um,))*"


def _compile(role_re: str) -> re.Pattern:
    return re.compile(rf"\b{_SELF}{_FILLER}\s+(?:{role_re})\b", re.I)


_COMPILED = {role: _compile(p) for role, p in _ROLE_PATTERNS.items()}


def detect_self_introductions(m: Meeting) -> list[dict]:
    """Return [{speaker, role, turn_idx, quote}] from explicit self-introductions."""
    found: dict[str, dict] = {}
    conflicts: set[str] = set()
    for t in m.turns:
        for role, rx in _COMPILED.items():
            mt = rx.search(t.text)
            if not mt:
                continue
            prev = found.get(t.speaker)
            if prev and prev["role"] != role:
                conflicts.add(t.speaker)
                continue
            if not prev:
                # Quote: the sentence around the match, cut from the turn verbatim.
                s = t.text.rfind(".", 0, mt.start()) + 1
                e = t.text.find(".", mt.end())
                quote = t.text[s : e if e != -1 else len(t.text)].strip()
                found[t.speaker] = {"speaker": t.speaker, "role": role, "turn_idx": t.idx, "quote": quote}
    for sp in conflicts:
        found.pop(sp, None)
    # A role should belong to exactly one speaker in a meeting.
    by_role = defaultdict(list)
    for r in found.values():
        by_role[r["role"]].append(r["speaker"])
    return [r for r in found.values() if len(by_role[r["role"]]) == 1]


def merge_roles(rows: list[dict]) -> dict[str, dict[str, dict]]:
    """rows from the store -> {meeting_id: {speaker: {role, source, quote, turn_idx}}}.
    Regex beats model; a role claimed by two speakers in one meeting is dropped."""
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    rank = {"intro_regex": 0, "llm": 1}
    for r in sorted(rows, key=lambda r: rank.get(r["source"], 9)):
        mid, sp = r["meeting_id"], r["speaker"]
        if sp in out[mid]:
            continue
        if any(v["role"] == r["role"] for v in out[mid].values()):
            continue
        out[mid][sp] = {"role": r["role"], "source": r["source"], "quote": r["quote"], "turn_idx": r["turn_idx"],
                        "name": r["name"] if "name" in r.keys() else ""}
    return dict(out)


def normalize_role(text: str) -> str | None:
    t = text.lower()
    for role, p in _ROLE_PATTERNS.items():
        if re.search(p, t):
            return role
    if re.search(r"\bpm\b|manager", t):
        return "Project Manager"
    return None
