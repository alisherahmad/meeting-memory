import pytest

from conftest import MEETING_A
from meeting_memory.chunking import chunk_meeting
from meeting_memory.quotes import quote_is_valid, resolve_quote, trim_quote
from meeting_memory.transcripts import TranscriptParseError, parse_transcript, split_meeting_id


def test_parse_header_and_turns(meetings):
    a = meetings[0]
    assert a.meeting_id == "ZZ0001a" and a.team == "ZZ0001" and a.ordinal == 1
    assert [t.speaker for t in a.turns] == ["A", "B", "C", "A"]
    assert a.turns[1].start_time == "00:00:10" and a.turns[1].start_seconds == 10
    assert a.turns[1].text.startswith("Hi, I'm the Industrial Designer.")


def test_parse_rejects_team_mismatch():
    with pytest.raises(TranscriptParseError):
        parse_transcript(MEETING_A.replace("Team: ZZ0001", "Team: XX9999"))


def test_parse_rejects_no_turns():
    with pytest.raises(TranscriptParseError):
        parse_transcript("Meeting: ZZ0001a\nTeam: ZZ0001\n")


def test_split_meeting_id():
    assert split_meeting_id("TS3012d") == ("TS3012", "d")
    with pytest.raises(TranscriptParseError):
        split_meeting_id("bad")


def test_chunks_cover_all_turns_without_splitting(meetings):
    m = meetings[0]
    chunks = chunk_meeting(m, target_words=15, stride_words=8)
    covered = set()
    for s, e, text in chunks:
        covered.update(range(s, e + 1))
        assert text.startswith(f"[{s}]")
    assert covered == {t.idx for t in m.turns}


def test_exact_quote_case_and_space_insensitive(meetings):
    turns = meetings[0].turns
    rq = resolve_quote(turns, "i think we SHOULD use   uh solar cells", 1)
    assert rq and rq.method == "exact" and rq.quote == "I think we should use uh solar cells"
    assert rq.quote in turns[1].text  # exact substring of the original


def test_relocated_when_turn_index_wrong(meetings):
    rq = resolve_quote(meetings[0].turns, "Solar cells sound expensive to me", 0)
    assert rq and rq.turn_idx == 2 and rq.method == "relocated"


def test_repair_dropped_filler_word(meetings):
    turns = meetings[0].turns
    rq = resolve_quote(turns, "I think we should use solar cells as the energy source", 1)
    assert rq and rq.method == "repaired"
    assert rq.quote in turns[1].text and "uh solar" in rq.quote


def test_rejects_short_and_invented_quotes(meetings):
    turns = meetings[0].turns
    assert resolve_quote(turns, "solar cells", 1) is None
    assert resolve_quote(turns, "we decided to build a flying toaster with wings", None) is None


def test_quote_must_be_within_one_turn(meetings):
    # Words spanning the end of turn 1 and the start of turn 2 must not verify.
    spanning = "because they never run out. I'm the marketing expert."
    assert resolve_quote(meetings[0].turns, spanning, 1) is None
    assert not quote_is_valid([t.text for t in meetings[0].turns], spanning)


def test_trim_keeps_exact_substring():
    q = "one  two three four five six seven"
    t = trim_quote(q, max_words=6)
    assert t == "one  two three four five six" and q.startswith(t)
