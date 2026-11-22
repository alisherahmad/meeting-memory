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
    Constraint-resolved roles beat regex, regex beats model; a role claimed by two
    speakers in one meeting is dropped."""
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    rank = {"resolved": 0, "intro_regex": 1, "llm": 2}
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


# ---------------------------------------------------------------------------
# Deterministic cross-check: "a speaker who mentions a person by name is not that
# person". Model-assigned roles can carry an earlier meeting's letter mapping
# across a swap (IS1000 c -> d). Names tie people to roles across the team's
# meetings; name mentions inside a meeting rule out assignments; the closest
# assignment that satisfies every constraint wins.
# ---------------------------------------------------------------------------
from collections import Counter  # noqa: E402
from itertools import permutations  # noqa: E402

def team_name_roles(rows: list[dict]) -> dict[str, str]:
    """Majority role per participant name across a team's role rows (names come
    from model role claims that were verified against the speaker's own turn)."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        name = (r.get("name") or "").strip()
        if name and r["source"] != "resolved" and re.fullmatch(r"[A-Z][a-z]{2,}", name.split()[0]):
            votes[name.split()[0]][r["role"]] += 1
    out = {}
    for name, c in votes.items():
        (role, n), *rest = c.most_common()
        if not rest or n > rest[0][1]:
            out[name] = role
    # A role claimed by two different names is ambiguous: drop both.
    by_role = Counter(out.values())
    return {n: r for n, r in out.items() if by_role[r] == 1}


def _vocative_patterns(name: str) -> list[re.Pattern]:
    n = re.escape(name)
    return [
        re.compile(rf",\s*{n}\s*\?"),                                         # "Right, Matthew?"
        re.compile(rf"\b(?:thank you|thanks)(?: very much)?,?\s+{n}\b", re.I),  # "Thank you very much Brian"
        re.compile(rf"\b{n}\s*,?\s+(?:you|can you|could you|would you|do you|will you)\b"),  # "So Paul, you can"
        re.compile(rf"\bwhat (?:do|did) you (?:say|think),?\s+{n}\b", re.I),   # "What do you say, Mael?"
    ]


def name_mentions(turns, names) -> dict[str, set[str]]:
    """speaker -> names they ADDRESS directly (vocatives). Plain mentions are not
    used: people often say their own name ("me again, Rajan the Marketing Expert",
    "Abdul al-Hasred is my name"), which made a broader rule wrong 9 times in 11."""
    out: dict[str, set[str]] = defaultdict(set)
    for name in names:
        pats = _vocative_patterns(name)
        for t in turns:
            if any(p.search(t.text) for p in pats):
                out[t.speaker].add(name)
    return out


def resolve_meeting_roles(current: dict[str, dict], speakers: list[str], mentions: dict[str, set[str]],
                          name_role: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Return ({speaker: role}, notes). Hard constraint: speaker S never holds the
    role of a person S mentions by name. Among valid one-to-one assignments, pick
    the one that changes the fewest current roles (regex roles weigh 3x)."""
    forbidden = {sp: {name_role[n] for n in mentions.get(sp, ()) if n in name_role} for sp in speakers}
    cur = {sp: v["role"] for sp, v in current.items() if sp in speakers}
    if all(cur.get(sp) not in forbidden[sp] for sp in cur) or len(speakers) > len(ROLES):
        return cur, []
    best, best_score = None, -1
    for perm in permutations(ROLES, len(speakers)):
        assign = dict(zip(speakers, perm))
        if any(assign[sp] in forbidden[sp] for sp in speakers):
            continue
        score = sum((3 if current.get(sp, {}).get("source") == "intro_regex" else 1)
                    for sp in speakers if cur.get(sp) == assign[sp])
        # Tiebreak: a speaker's recorded name corroborates the role that name holds
        # in the team, unless the speaker mentions that very name (then the claim is wrong).
        for sp in speakers:
            nm = ((current.get(sp) or {}).get("name") or "").split(" ")[0]
            if nm and name_role.get(nm) == assign[sp] and nm not in mentions.get(sp, ()):
                score += 0.5
        if score > best_score:
            best, best_score = assign, score
    if best is None:
        return cur, ["no assignment satisfies the name constraints; kept model roles"]
    notes = [f"{sp}: {cur.get(sp, '?')} -> {best[sp]} (mentions {', '.join(sorted(mentions.get(sp, ())))})"
             for sp in speakers if cur.get(sp) != best[sp]]
    return best, notes


def resolve_team_roles(store, team: str) -> dict[str, list[str]]:
    """Recompute 'resolved' roles for every meeting of a team; returns change notes per meeting."""
    rows = [dict(r) for r in store.roles(team)]
    name_role = team_name_roles(rows)
    role_name = {r: n for n, r in name_role.items()}
    merged = merge_roles([r for r in rows if r["source"] != "resolved"])
    changes: dict[str, list[str]] = {}
    for m in store.meetings(team):
        mid = m["meeting_id"]
        turns = store.turns(mid)
        speakers = sorted({t.speaker for t in turns})
        current = merged.get(mid, {})
        if len(current) < len(speakers):
            store.set_roles(team, mid, "resolved", [])
            continue  # incomplete mapping: nothing to permute safely
        assign, notes = resolve_meeting_roles(current, speakers, name_mentions(turns, name_role), name_role)
        rows_out = []
        for sp, role in assign.items():
            kept = current.get(sp, {})
            same = kept.get("role") == role
            rows_out.append({"speaker": sp, "role": role, "turn_idx": kept.get("turn_idx") if same else None,
                             "quote": kept.get("quote") if same else None,
                             "name": (kept.get("name") if same else role_name.get(role, "")) or ""})
        store.set_roles(team, mid, "resolved", rows_out if notes else [])
        if notes:
            changes[mid] = notes
    return changes
