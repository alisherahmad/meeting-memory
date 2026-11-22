from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import MEETING_A, MEETING_B
from meeting_memory.ingest import run_ingest
from meeting_memory.llm import LLM
from meeting_memory.server import create_app
from meeting_memory.store import Store


@pytest.fixture
def client(settings, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    d = Path(settings.transcripts_dir)
    d.mkdir(parents=True)
    (d / "ZZ0001a.txt").write_text(MEETING_A, encoding="utf-8")
    (d / "ZZ0001b.txt").write_text(MEETING_B, encoding="utf-8")
    store = Store(settings.db_path)
    run_ingest(settings, store, LLM(settings, store), on_event=lambda s: None)
    return TestClient(create_app(settings))


def test_status_and_teams(client):
    s = client.get("/api/status").json()
    assert s["meetings"] == 2 and s["llm_available"] is False
    assert client.get("/api/teams").json()[0]["team"] == "ZZ0001"


def test_ask_without_key_is_503_and_input_validated(client):
    assert client.post("/api/ask", json={"question": "What did ZZ0001 decide?"}).status_code == 503
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/api/ask", json={"question": "valid question here", "team": "../../x"}).status_code == 422


def test_turns_and_memory_endpoints(client):
    turns = client.get("/api/meetings/ZZ0001b/turns?start=1&end=2").json()
    assert [t["idx"] for t in turns] == [1, 2]
    assert client.get("/api/meetings/NOPE00a/turns").status_code == 404
    mem = client.get("/api/teams/ZZ0001/memory?as_of=1").json()
    assert mem["as_of"] == 1 and len(mem["meetings"]) == 2
    assert client.get("/api/teams/QQ9999/memory").status_code == 404


def test_brief_falls_back_without_model(client):
    r = client.post("/api/brief", json={"team": "ZZ0001", "before": "ZZ0001b", "use_llm": True})
    assert r.status_code == 200 and r.json()["mode"] == "deterministic"
    assert client.post("/api/brief", json={"team": "ZZ0001", "before": "ZZ0001a"}).status_code == 400


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Meeting Memory" in r.text
