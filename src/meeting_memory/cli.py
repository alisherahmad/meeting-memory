"""Command line: python -m meeting_memory <command> ...

  ingest        parse + index (+ extract memory with the LLM unless --no-extract)
  ask           answer one question with the agent
  answer-all    run the agent on questions.json and write answers.json (+ brief)
  brief         write a pre-meeting brief for a team
  stats         ingest/LLM cost ledger summary
  serve         start the web UI
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .agent import Agent
from .brief import generate_brief
from .config import PROJECT_ROOT, get_settings
from .ingest import run_ingest
from .llm import LLM
from .retrieval import Retriever
from .store import Store


def _build(settings):
    store = Store(settings.db_path)
    llm = LLM(settings, store)
    retriever = Retriever(store, settings.embedding_model if settings.use_embeddings else None)
    return store, llm, retriever


def _require_llm(llm: LLM) -> None:
    if not llm.available:
        sys.exit("No ANTHROPIC_API_KEY configured. Put it in .env (see .env.example).")


def cmd_ingest(args, settings) -> None:
    store, llm, _ = _build(settings)
    teams = set(args.teams.split(",")) if args.teams else None
    rep = run_ingest(settings, store, llm, extract=not args.no_extract, force=args.force, only_teams=teams)
    out = rep.as_dict()
    out["extracted"] = len(rep.extracted)
    out["extraction_skipped"] = len(rep.extraction_skipped)
    print(json.dumps(out, indent=2, default=str))
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(rep.as_dict(), indent=2, default=str), encoding="utf-8")


def _print_event(ev) -> None:
    print(f"  step {ev.step:>2} {ev.kind:<16} {ev.name:<18} {ev.detail[:150]}", file=sys.stderr)


def cmd_ask(args, settings) -> None:
    store, llm, retriever = _build(settings)
    _require_llm(llm)
    res = Agent(settings, store, llm, retriever).answer(args.question, team=args.team, on_event=_print_event)
    print(json.dumps({k: v for k, v in res.as_dict().items() if k != "trace"}, indent=2))


def cmd_answer_all(args, settings) -> None:
    store, llm, retriever = _build(settings)
    _require_llm(llm)
    spec = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    questions = spec["questions"]
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["question_id"] in wanted]
    agent = Agent(settings, store, llm, retriever)

    def run(q):
        t = time.monotonic()
        r = agent.answer(q["question"], team=q.get("team"))
        print(f"{q['question_id']} {r.state} steps={r.steps} cites={len(r.citations)} {time.monotonic() - t:.0f}s ${r.usage.cost_usd:.3f}",
              file=sys.stderr)
        return q, r

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(run, questions))

    run_dir = Path(args.run_dir or PROJECT_ROOT / "evaluation" / "results" / f"run_{datetime.now():%Y%m%d_%H%M%S}")
    run_dir.mkdir(parents=True, exist_ok=True)
    answers = [
        {"question_id": q["question_id"], "answer": r.answer or "No answer could be verified.",
         "citations": [{"meeting_id": c["meeting_id"], "quote": c["quote"]} for c in r.citations]}
        for q, r in results
    ]
    brief_text = ""
    if spec.get("brief_task") and not args.skip_brief:
        b = generate_brief(store, llm, spec["brief_task"]["team"], model=settings.agent_model, effort=settings.agent_effort)
        brief_text = b.as_text()
        (run_dir / "brief.json").write_text(json.dumps(b.as_dict(), indent=2), encoding="utf-8")
    out = {"answers": answers, "brief": brief_text}
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "agent_runs.json").write_text(
        json.dumps([{"question_id": q["question_id"], **r.as_dict()} for q, r in results], indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"wrote {args.out} and {run_dir}", file=sys.stderr)


def cmd_brief(args, settings) -> None:
    store, llm, _ = _build(settings)
    b = generate_brief(store, llm, args.team, before_meeting=args.before, model=settings.agent_model,
                       effort=settings.agent_effort, use_llm=not args.no_llm)
    if args.json:
        print(json.dumps(b.as_dict(), indent=2))
    else:
        print(b.as_text())


def cmd_stats(args, settings) -> None:
    store, _, _ = _build(settings)
    rows = store.query("""SELECT purpose, model, COUNT(*) calls, SUM(ok) ok, SUM(input_tokens) inp, SUM(output_tokens) outp,
                          SUM(cache_read) cr, SUM(cache_write) cw, ROUND(SUM(cost_usd),4) cost, ROUND(AVG(latency_ms)) avg_ms
                          FROM llm_calls GROUP BY purpose, model""")
    print(json.dumps([dict(r) for r in rows], indent=2))
    m = store.query("SELECT COUNT(*) n, SUM(n_words) w, SUM(extracted_hash IS NOT NULL) ex FROM meetings")[0]
    i = store.query("SELECT COUNT(*) n, SUM(verified) v FROM items")[0]
    print(json.dumps({"meetings": m["n"], "words": m["w"], "extracted": m["ex"], "items": i["n"], "items_verified": i["v"]}, indent=2))


def cmd_serve(args, settings) -> None:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="meeting_memory")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ingest")
    a.add_argument("--no-extract", action="store_true", help="parse/index only, no LLM")
    a.add_argument("--force", action="store_true", help="re-extract even if unchanged")
    a.add_argument("--teams", help="comma-separated team ids")
    a.add_argument("--report", help="write the ingest report JSON here")
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--team")
    a = sub.add_parser("answer-all")
    a.add_argument("--questions", default=str(PROJECT_ROOT / "data" / "questions.json"))
    a.add_argument("--out", default=str(PROJECT_ROOT / "answers.json"))
    a.add_argument("--only", help="comma-separated question ids")
    a.add_argument("--concurrency", type=int, default=4)
    a.add_argument("--run-dir")
    a.add_argument("--skip-brief", action="store_true")
    a = sub.add_parser("brief")
    a.add_argument("--team", required=True)
    a.add_argument("--before", help="meeting id the brief prepares for (default: the team's final meeting)")
    a.add_argument("--no-llm", action="store_true")
    a.add_argument("--json", action="store_true")
    sub.add_parser("stats")
    a = sub.add_parser("serve")
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    settings = get_settings()
    {"ingest": cmd_ingest, "ask": cmd_ask, "answer-all": cmd_answer_all, "brief": cmd_brief, "stats": cmd_stats,
     "serve": cmd_serve}[args.cmd](args, settings)


if __name__ == "__main__":
    main()
