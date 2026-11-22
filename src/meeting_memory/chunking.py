"""Turn-aligned overlapping windows for retrieval. Deterministic.

Chunks never split a speaker turn (citations must come from one turn), and each
chunk carries its turn range so the agent can expand context with read_turns.
"""

from __future__ import annotations

from .transcripts import Meeting, Turn

TARGET_WORDS = 220
STRIDE_WORDS = 110
MAX_TURN_CHARS_IN_CHUNK = 1200


def format_turn(t: Turn, max_chars: int | None = None) -> str:
    text = t.text
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " …"
    return f"[{t.idx}] {t.speaker}: {text}"


def chunk_meeting(m: Meeting, target_words: int = TARGET_WORDS, stride_words: int = STRIDE_WORDS) -> list[tuple[int, int, str]]:
    """Return (start_idx, end_idx, text) windows of ~target_words, starting every ~stride_words."""
    turns = m.turns
    words = [max(1, len(t.text.split())) for t in turns]
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(turns):
        end, total = start, 0
        while end < len(turns) and (total < target_words or end == start):
            total += words[end]
            end += 1
        text = "\n".join(format_turn(t, MAX_TURN_CHARS_IN_CHUNK) for t in turns[start:end])
        chunks.append((turns[start].idx, turns[end - 1].idx, text))
        if end >= len(turns):
            break
        # Advance by ~stride_words, at least one turn.
        adv, nxt = 0, start
        while nxt < end - 1 and adv < stride_words:
            adv += words[nxt]
            nxt += 1
        start = max(nxt, start + 1)
    return chunks
