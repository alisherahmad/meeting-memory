"""Deterministic transcript parsing. No LLM involved.

File format (Catalist reformatting of the AMI corpus):
    Meeting: TS3012a
    Team: TS3012
    ...header lines...

    00:00:02 Speaker A
    turn text

    00:00:03 Speaker B
    ...
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

MEETING_ID_RE = re.compile(r"^(?P<team>[A-Z]{2}\d{4})(?P<letter>[a-z])$")
TURN_HEADER_RE = re.compile(r"^(?P<time>\d{2}:\d{2}:\d{2}) Speaker (?P<speaker>[A-Z])\s*$")
HEADER_RE = re.compile(r"^(?P<key>[A-Za-z ]+):\s*(?P<value>.*)$")


class TranscriptParseError(ValueError):
    pass


@dataclass(frozen=True)
class Turn:
    idx: int
    start_time: str  # HH:MM:SS from start of recording
    speaker: str  # "A".."D"
    text: str

    @property
    def start_seconds(self) -> int:
        h, m, s = (int(x) for x in self.start_time.split(":"))
        return h * 3600 + m * 60 + s


@dataclass
class Meeting:
    meeting_id: str
    team: str
    letter: str  # a, b, c, d
    turns: list[Turn]
    header: dict[str, str] = field(default_factory=dict)
    content_hash: str = ""

    @property
    def ordinal(self) -> int:
        """Position in the team's series: a=1, b=2, ... (used to order memory in time)."""
        return ord(self.letter) - ord("a") + 1

    @property
    def n_words(self) -> int:
        return sum(len(t.text.split()) for t in self.turns)

    @property
    def speakers(self) -> list[str]:
        return sorted({t.speaker for t in self.turns})


def split_meeting_id(meeting_id: str) -> tuple[str, str]:
    m = MEETING_ID_RE.match(meeting_id)
    if not m:
        raise TranscriptParseError(f"Unrecognised meeting id: {meeting_id!r}")
    return m.group("team"), m.group("letter")


def parse_transcript(text: str, meeting_id: str | None = None) -> Meeting:
    lines = text.replace("\r\n", "\n").split("\n")
    header: dict[str, str] = {}
    i = 0
    # Header: "Key: value" lines until the first turn header.
    while i < len(lines) and not TURN_HEADER_RE.match(lines[i]):
        hm = HEADER_RE.match(lines[i])
        if hm:
            header[hm.group("key").strip()] = hm.group("value").strip()
        i += 1

    mid = meeting_id or header.get("Meeting")
    if not mid:
        raise TranscriptParseError("No meeting id in header and none supplied")
    team, letter = split_meeting_id(mid)
    if header.get("Team") and header["Team"] != team:
        raise TranscriptParseError(f"Header team {header['Team']} does not match id {mid}")

    turns: list[Turn] = []
    cur_time = cur_speaker = None
    buf: list[str] = []

    def flush() -> None:
        if cur_time is None:
            return
        body = " ".join(s.strip() for s in buf if s.strip())
        turns.append(Turn(idx=len(turns), start_time=cur_time, speaker=cur_speaker, text=body))

    for line in lines[i:]:
        tm = TURN_HEADER_RE.match(line)
        if tm:
            flush()
            cur_time, cur_speaker, buf = tm.group("time"), tm.group("speaker"), []
        else:
            buf.append(line)
    flush()

    if not turns:
        raise TranscriptParseError(f"{mid}: no speaker turns found")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return Meeting(meeting_id=mid, team=team, letter=letter, turns=turns, header=header, content_hash=digest)


def load_transcript(path: Path) -> Meeting:
    return parse_transcript(path.read_text(encoding="utf-8"), meeting_id=path.stem)


def discover_transcripts(directory: Path) -> list[Path]:
    """All transcript files, sorted so each team's meetings come in series order."""
    paths = [p for p in directory.glob("*.txt") if MEETING_ID_RE.match(p.stem)]
    return sorted(paths, key=lambda p: (p.stem[:-1], p.stem[-1]))
