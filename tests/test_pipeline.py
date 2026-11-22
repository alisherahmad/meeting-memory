import json
from pathlib import Path

from conftest import MEETING_A, MEETING_B, FakeBackend, message, text_block
from meeting_memory.brief import generate_brief
from meeting_memory.extraction import validate_extraction
from meeting_memory.ingest import run_ingest
from meeting_memory.llm import LLM, LLMError
from meeting_memory.retrieval import Retriever, team_from_text
from meeting_memory.roles import detect_self_introductions
from meeting_memory.store import Store, fts_query


# ---- store / retrieval ------------------------------------------------------------
def test_upsert_is_idempotent(store, meetings):
    from meeting_memory.chunking import chunk_meeting

    assert store.upsert_meeting(meetings[0], chunk_meeting(meetings[0])) is False
    assert len(store.turns("ZZ0001a")) == 4


def test_fts_query_neutralises_syntax():
    q = fts_query('solar" OR NEAR(x) AND -cells* {team}:')
    assert '"solar"' in q and "NEAR(" not in q and "*" not in q and "{" not in q


def test_bm25_search_is_team_scoped(store):
    r = Retriever(store, None)
    hits = r.search_chunks("rechargeable battery", team="ZZ0001", limit=3, mode="bm25")
    assert hits and all(h.team == "ZZ0001" for h in hits)
    assert r.search_chunks("rechargeable battery", team="QQ0000", mode="bm25") == []
    assert r.search_chunks('"; DROP TABLE turns; --', team="ZZ0001", mode="bm25") is not None
    assert len(store.turns("ZZ0001b")) == 5


def test_team_from_text():
    assert team_from_text("Team TS3006 planned both") == "TS3006"
    assert team_from_text("no team here") is None


def test_regex_roles(meetings):
    roles = {r["speaker"]: r["role"] for r in detect_self_introductions(meetings[0])}
    assert roles == {"A": "Project Manager", "B": "Industrial Designer", "C": "Marketing Expert"}


# ---- extraction validation -----------------------------------------------------------
def test_validate_extraction_enforces_contracts(store, meetings):
    m = meetings[0]
    raw = {
        "summary": "Kick-off.",
        "roles": [
            {"speaker": "A", "role": "Project Manager", "name": "", "turn": 0, "quote": "I'm the Project Manager for this project"},
            {"speaker": "B", "role": "Marketing Expert", "name": "", "turn": 1, "quote": "this sentence was never said by anyone at all"},
        ],
        "items": [
            {"kind": "decision", "thread": "new:energy", "topic": "energy source", "relation": "new", "related": [],
             "statement": "Use solar cells.", "speakers": ["A", "Z"], "owner": "", "value": "",
             "evidence": [{"turn": 3, "quote": "for now we go with solar cells as the energy source"}]},
            {"kind": "action_item", "thread": "new:prices", "topic": "prices", "relation": "new", "related": ["@0", "@5", "ZZ0001c-001"],
             "statement": "B checks prices.", "speakers": ["A"], "owner": "b", "value": "",
             "evidence": [{"turn": 3, "quote": "B will check prices of the components for next time"}]},
            {"kind": "gossip", "thread": "new:x", "topic": "x", "relation": "new", "related": [], "statement": "x",
             "speakers": [], "owner": "", "value": "", "evidence": []},
            {"kind": "objection", "thread": "ZZ0001x-T99", "topic": "energy source", "relation": "new", "related": [],
             "statement": "C worries about cost.", "speakers": ["C"], "owner": "", "value": "",
             "evidence": [{"turn": 2, "quote": "totally invented words that do not appear here"}]},
        ],
    }
    res = validate_extraction(raw, m, store)
    assert res.stats["dropped_kind"] == 1 and res.stats["unknown_thread"] == 1
    assert [i["item_id"] for i in res.items] == ["ZZ0001a-001", "ZZ0001a-002", "ZZ0001a-003"]
    d, act, obj = res.items
    assert d["speakers"] == ["A"] and d["verified"]
    assert d["evidence"][0]["quote"] in m.turns[3].text
    assert act["related"] == ["ZZ0001a-001"] and act["owner"] == "B"  # @0 kept; forward @5 and unknown id dropped
    assert act["evidence"][0]["quote"] in m.turns[3].text  # repaired ("the" was missing)
    assert not obj["verified"] and obj["evidence"] == []
    assert [r["speaker"] for r in res.roles] == ["A"]  # unverifiable role claim dropped
    assert d["thread_id"] == "ZZ0001a-T01" and act["thread_id"] == "ZZ0001a-T02"


# ---- ingest end to end with a fake model -------------------------------------------
def _extraction_for(meeting_id):
    if meeting_id.endswith("a"):
        return {"summary": "Chose solar cells.", "roles": [], "items": [
            {"kind": "decision", "thread": "new:energy", "topic": "energy source", "relation": "new", "related": [],
             "statement": "Use solar cells as the energy source.", "speakers": ["A"], "owner": "", "value": "",
             "evidence": [{"turn": 3, "quote": "for now we go with solar cells as the energy source"}]},
            {"kind": "action_item", "thread": "new:prices", "topic": "component prices", "relation": "new", "related": [],
             "statement": "B checks component prices.", "speakers": ["A"], "owner": "B", "value": "",
             "evidence": [{"turn": 3, "quote": "B will check the prices of the components for next time"}]},
        ]}
    return {"summary": "Switched to battery.", "roles": [], "items": [
        {"kind": "report", "thread": "ZZ0001a-T02", "topic": "component prices", "relation": "fulfils", "related": ["ZZ0001a-002"],
         "statement": "B reports solar cells cost 4 EUR each.", "speakers": ["B"], "owner": "", "value": "4 EUR",
         "evidence": [{"turn": 1, "quote": "the solar cells cost four euros each, which is way too much"}]},
        {"kind": "decision", "thread": "ZZ0001a-T01", "topic": "energy source", "relation": "replaces", "related": ["ZZ0001a-001"],
         "statement": "Drop solar cells; use a rechargeable battery.", "speakers": ["A", "C"], "owner": "", "value": "",
         "evidence": [{"turn": 3, "quote": "we drop the solar cells and use a rechargeable battery"}]},
    ]}


def _fake_extractor(kwargs):
    user = kwargs["messages"][0]["content"]
    mid = "ZZ0001b" if "CURRENT MEETING: ZZ0001b" in user else "ZZ0001a"
    if mid == "ZZ0001b":
        assert "ZZ0001a-001 [decision, current]" in user  # prior memory is passed forward
    return message([text_block(json.dumps(_extraction_for(mid)))], stop="end_turn")


def _write_corpus(settings):
    d = Path(settings.transcripts_dir)
    d.mkdir(parents=True)
    (d / "ZZ0001a.txt").write_text(MEETING_A, encoding="utf-8")
    (d / "ZZ0001b.txt").write_text(MEETING_B, encoding="utf-8")


def test_ingest_builds_time_aware_memory(settings):
    _write_corpus(settings)
    store = Store(settings.db_path)
    llm = LLM(settings, store, backend=FakeBackend([_fake_extractor, _fake_extractor]))
    rep = run_ingest(settings, store, llm, on_event=lambda s: None)
    assert sorted(rep.extracted) == ["ZZ0001a", "ZZ0001b"] and not rep.extraction_failed
    from meeting_memory.memory import compute_state

    st = {s.item["item_id"]: s.status for ts in compute_state(store.items("ZZ0001")).values() for s in ts.items}
    assert st["ZZ0001a-001"] == "superseded" and st["ZZ0001b-002"] == "current" and st["ZZ0001a-002"] == "done"
    assert store.query("SELECT COUNT(*) n FROM llm_calls")[0]["n"] == 2

    # Re-running is a no-op (idempotent), no model calls needed.
    rep2 = run_ingest(settings, store, LLM(settings, store, backend=FakeBackend([])), on_event=lambda s: None)
    assert sorted(rep2.extraction_skipped) == ["ZZ0001a", "ZZ0001b"]

    # Brief before meeting b only sees meeting a: solar cells are still current, the price action is open.
    b = generate_brief(store, llm, "ZZ0001", before_meeting="ZZ0001b", use_llm=False)
    assert b.based_on == ["ZZ0001a"]
    text = b.as_text()
    assert "Use solar cells" in text and "B checks component prices" in text and "rechargeable" not in text
    for pts in b.sections.values():
        for p in pts:
            for c in p.citations:
                assert c["quote"] in MEETING_A


def test_ingest_failure_blocks_later_meetings(settings):
    _write_corpus(settings)
    store = Store(settings.db_path)
    llm = LLM(settings, store, backend=FakeBackend([LLMError("boom", retryable=True)]))
    rep = run_ingest(settings, store, llm, on_event=lambda s: None)
    assert "ZZ0001a" in rep.extraction_failed and rep.blocked == ["ZZ0001b"] and not rep.extracted
    assert store.query("SELECT ok FROM llm_calls")[0]["ok"] == 0


def test_ingest_without_credentials_still_indexes(settings, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    _write_corpus(settings)
    store = Store(settings.db_path)
    rep = run_ingest(settings, store, LLM(settings, store), on_event=lambda s: None)
    assert rep.meetings_parsed == 2 and not rep.extracted and "no ANTHROPIC_API_KEY" in rep.embeddings_note
