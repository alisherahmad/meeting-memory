"""Local web UI + JSON API. Binds to 127.0.0.1 by default; there is no auth, so it
is a single-user local tool, not a deployable multi-tenant service."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Agent
from .brief import generate_brief
from .config import PROJECT_ROOT, Settings
from .llm import LLM
from .memory import compute_state, last_activity, thread_to_dict
from .retrieval import Retriever
from .roles import merge_roles
from .store import Store

STATIC = Path(__file__).parent / "static"
TEAM_PATTERN = r"^[A-Z]{2}\d{4}$"
MEETING_PATTERN = r"^[A-Z]{2}\d{4}[a-z]$"


class AskBody(BaseModel):
    question: str = Field(min_length=5, max_length=600)
    team: str | None = Field(default=None, pattern=TEAM_PATTERN)


class BriefBody(BaseModel):
    team: str = Field(pattern=TEAM_PATTERN)
    before: str | None = Field(default=None, pattern=MEETING_PATTERN)
    use_llm: bool = True


def create_app(settings: Settings) -> FastAPI:
    store = Store(settings.db_path)
    llm = LLM(settings, store)
    retriever = Retriever(store, settings.embedding_model if settings.use_embeddings else None)
    agent = Agent(settings, store, llm, retriever)
    runs = threading.BoundedSemaphore(2)  # caps concurrent paid agent runs

    app = FastAPI(title="Meeting Memory", docs_url="/api/docs")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        m = store.query("SELECT COUNT(*) n, SUM(n_words) w, SUM(extracted_hash IS NOT NULL) ex FROM meetings")[0]
        i = store.query("SELECT COUNT(*) n, SUM(verified) v FROM items")[0]
        c = store.query("SELECT COUNT(*) n, SUM(embedding IS NOT NULL) e FROM chunks")[0]
        cost = store.query("SELECT ROUND(SUM(cost_usd),3) c FROM llm_calls")[0]["c"] or 0
        return {"meetings": m["n"], "words": m["w"] or 0, "extracted": m["ex"] or 0, "items": i["n"], "items_verified": i["v"] or 0,
                "chunks": c["n"], "chunks_embedded": c["e"] or 0, "llm_available": llm.available, "agent_model": settings.agent_model,
                "spent_usd": cost}

    @app.get("/api/teams")
    def teams():
        rows = store.query("SELECT team, GROUP_CONCAT(meeting_id) mids, SUM(extracted_hash IS NOT NULL) ex FROM meetings GROUP BY team ORDER BY team")
        return [{"team": r["team"], "meetings": sorted(r["mids"].split(",")), "extracted": r["ex"]} for r in rows]

    @app.get("/api/teams/{team}/memory")
    def team_memory(team: str, as_of: int | None = None):
        if not store.meetings(team):
            raise HTTPException(404, "unknown team")
        state = compute_state(store.items(team), as_of_ordinal=as_of)
        threads = sorted(state.values(), key=last_activity, reverse=True)
        meetings = [{"meeting_id": r["meeting_id"], "ordinal": r["ordinal"], "summary": r["summary"], "n_turns": r["n_turns"]}
                    for r in store.meetings(team)]
        return {"team": team, "as_of": as_of, "meetings": meetings, "roles": merge_roles([dict(r) for r in store.roles(team)]),
                "threads": [thread_to_dict(t) for t in threads]}

    @app.get("/api/meetings/{meeting_id}/turns")
    def turns(meeting_id: str, start: int = 0, end: int | None = None):
        ts = store.turns(meeting_id, start, end)
        if not ts:
            raise HTTPException(404, "unknown meeting or range")
        return [{"idx": t.idx, "time": t.start_time, "speaker": t.speaker, "text": t.text} for t in ts]

    @app.get("/api/search")
    def search(q: str, team: str | None = None, limit: int = 6):
        hits = retriever.search_chunks(q[:300], team=team, limit=max(1, min(limit, 10)))
        return [h.__dict__ for h in hits]

    @app.get("/api/examples")
    def examples():
        out = []
        qpath = PROJECT_ROOT / "data" / "questions.json"
        if qpath.exists():
            out += [{"id": q["question_id"], "team": q["team"], "question": q["question"], "set": "catalist"}
                    for q in json.loads(qpath.read_text(encoding="utf-8"))["questions"]]
        gpath = PROJECT_ROOT / "evaluation" / "gold_set.json"
        if gpath.exists():
            out += [{"id": c["case_id"], "team": c["team"], "question": c["question"], "set": "gold"}
                    for c in json.loads(gpath.read_text(encoding="utf-8"))]
        return out

    @app.post("/api/ask")
    def ask(body: AskBody):
        if not llm.available:
            raise HTTPException(503, "No ANTHROPIC_API_KEY configured on the server.")
        if not runs.acquire(blocking=False):
            raise HTTPException(429, "Two questions are already running; try again shortly.")
        events: queue.Queue = queue.Queue()
        cancelled = threading.Event()

        def work():
            try:
                res = agent.answer(body.question, team=body.team, on_event=lambda ev: events.put(("trace", ev.as_dict())),
                                   should_cancel=cancelled.is_set)
                events.put(("result", {k: v for k, v in res.as_dict().items() if k != "trace"}))
            except Exception as e:  # surfaced to the client, never swallowed
                events.put(("error", {"message": f"{type(e).__name__}: {e}"}))
            finally:
                events.put(None)
                runs.release()

        threading.Thread(target=work, daemon=True).start()

        def stream():
            try:
                while True:
                    item = events.get()
                    if item is None:
                        break
                    kind, payload = item
                    yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            finally:
                cancelled.set()  # client went away: stop spending at the next step boundary

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/brief")
    def brief(body: BriefBody):
        if not store.meetings(body.team):
            raise HTTPException(404, "unknown team")
        try:
            b = generate_brief(store, llm, body.team, before_meeting=body.before, model=settings.agent_model,
                               effort=settings.agent_effort, use_llm=body.use_llm)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return b.as_dict()

    return app
