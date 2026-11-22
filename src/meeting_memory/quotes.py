"""Citation verification. Plain code, never an LLM.

The grader checks a quote as: >= 6 words, copied exactly from within one speaker
turn of the named meeting, ignoring case and spacing. We are stricter: every quote
we emit is an exact character substring of a stored turn, so it passes regardless
of how punctuation is compared.

`resolve_quote` also *repairs* near-misses deterministically (e.g. a model that
dropped an "uh"), but the repaired quote is always cut from the transcript itself,
never invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

MIN_QUOTE_WORDS = 6
MAX_QUOTE_WORDS = 60
_WORD_RE = re.compile(r"\S+")
_PUNCT_RE = re.compile(r"[^\w']+")


def normalize(s: str) -> str:
    """Grader-equivalent normalisation: lowercase, collapse whitespace."""
    return " ".join(s.lower().split())


def _token_key(tok: str) -> str:
    return _PUNCT_RE.sub("", tok.lower())


def word_count(s: str) -> int:
    return len(s.split())


@dataclass(frozen=True)
class ResolvedQuote:
    turn_idx: int
    quote: str  # exact substring of the turn text
    method: str  # "exact" | "repaired" | "relocated"


def _exact_span(turn_text: str, quote: str) -> str | None:
    """Find quote in turn ignoring case/whitespace; return the original substring."""
    nq = normalize(quote)
    if not nq:
        return None
    toks = [(m.start(), m.end(), m.group()) for m in _WORD_RE.finditer(turn_text)]
    qtoks = nq.split(" ")
    n = len(qtoks)
    low = [t[2].lower() for t in toks]
    for i in range(len(toks) - n + 1):
        # Fast path on the first and last tokens, then full compare. Tokens at the
        # edges may be partial (quote starting mid-token is not allowed: we require
        # whole-token alignment, which is what "copied words" means).
        if low[i] == qtoks[0] and low[i + n - 1] == qtoks[-1] and low[i : i + n] == qtoks:
            return turn_text[toks[i][0] : toks[i + n - 1][1]]
    # Allow edge tokens to be partial (e.g. quote ends before a trailing comma).
    if n >= 2:
        for i in range(len(toks) - n + 1):
            if low[i + 1 : i + n - 1] == qtoks[1:-1] and low[i].endswith(qtoks[0]) and low[i + n - 1].startswith(qtoks[-1]):
                start = toks[i][0] + len(toks[i][2]) - len(qtoks[0])
                end = toks[i + n - 1][0] + len(qtoks[-1])
                return turn_text[start:end]
    return None


def _fuzzy_span(turn_text: str, quote: str, min_ratio: float = 0.85) -> str | None:
    """Align quote tokens to turn tokens (punctuation/case-insensitive) and cut the
    covering span out of the original turn. Rejects weak alignments."""
    toks = [(m.start(), m.end(), _token_key(m.group())) for m in _WORD_RE.finditer(turn_text)]
    qkeys = [k for k in (_token_key(t) for t in quote.split()) if k]
    tkeys = [t[2] for t in toks]
    if len(qkeys) < MIN_QUOTE_WORDS or not tkeys:
        return None
    sm = SequenceMatcher(a=tkeys, b=qkeys, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None
    # Keep the densest run of blocks: start at the first block whose span is near.
    matched = sum(b.size for b in blocks)
    if matched / len(qkeys) < min_ratio:
        return None
    a_start = blocks[0].a
    a_end = blocks[-1].a + blocks[-1].size  # exclusive
    span_len = a_end - a_start
    # The covering span must not be much longer than the quote (no stitching
    # together distant fragments of a long turn).
    if span_len > len(qkeys) * 1.25 + 2:
        return None
    return turn_text[toks[a_start][0] : toks[a_end - 1][1]]


def resolve_quote(turns: Sequence, quote: str, turn_idx: int | None = None) -> ResolvedQuote | None:
    """Return a verified exact quote from `turns` (objects with .idx and .text).

    Order: exact match in the given turn; exact match anywhere in the meeting;
    fuzzy repair in the given turn; fuzzy repair anywhere (only if unique).
    """
    if word_count(quote) < MIN_QUOTE_WORDS:
        return None
    by_idx = {t.idx: t for t in turns}
    if turn_idx is not None and turn_idx in by_idx:
        span = _exact_span(by_idx[turn_idx].text, quote)
        if span:
            return ResolvedQuote(turn_idx, span, "exact")
    for t in turns:
        span = _exact_span(t.text, quote)
        if span:
            return ResolvedQuote(t.idx, span, "exact" if t.idx == turn_idx else "relocated")
    if turn_idx is not None and turn_idx in by_idx:
        span = _fuzzy_span(by_idx[turn_idx].text, quote)
        if span and word_count(span) >= MIN_QUOTE_WORDS:
            return ResolvedQuote(turn_idx, span, "repaired")
    hits = []
    for t in turns:
        span = _fuzzy_span(t.text, quote)
        if span and word_count(span) >= MIN_QUOTE_WORDS:
            hits.append(ResolvedQuote(t.idx, span, "repaired"))
            if len(hits) > 1:
                return None  # ambiguous: refuse rather than guess
    return hits[0] if hits else None


def quote_is_valid(turn_texts: Sequence[str], quote: str) -> bool:
    """Grader-equivalent check: >= 6 words and a whitespace/case-insensitive
    substring of a single turn."""
    if word_count(quote) < MIN_QUOTE_WORDS:
        return False
    nq = normalize(quote)
    return any(nq in normalize(t) for t in turn_texts)


def trim_quote(quote: str, max_words: int = MAX_QUOTE_WORDS) -> str:
    """Cut to the first `max_words` words while keeping it an exact substring."""
    matches = list(_WORD_RE.finditer(quote))
    if len(matches) <= max_words:
        return quote
    return quote[: matches[max_words - 1].end()]
