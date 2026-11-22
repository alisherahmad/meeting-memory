"""Evaluation: python -m meeting_memory.evaluate <command>

  build-gold        merge evaluation/gold_drafts/*.json -> evaluation/gold_set.json (quotes re-verified)
  retrieval         retrieval recall on the gold set: BM25 vs dense vs hybrid (no LLM)
  gold              run the agent on the gold set and score it
  check-answers     grader emulation for answers.json: citation format + verbatim checks (no LLM)

Scoring is deterministic first: key facts via surface-string matching (a cheap,
transparent proxy that over- and under-matches; see notes), citations via the same
verbatim check the brief describes. A human read of each answer is recorded
separately in docs/EVALUATION_REPORT.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .agent import Agent
from .config import PROJECT_ROOT, get_settings
from .llm import LLM
from .quotes import MIN_QUOTE_WORDS, normalize, quote_is_valid, word_count
from .retrieval import Retriever
from .store import Store

EVAL_DIR = PROJECT_ROOT / "evaluation"
AMBIGUOUS = {"G-TS3008-2"}  # flagged by the case author: final-meeting outcome is never stated outright


def _store(settings) -> Store:
    return Store(settings.db_path)


def build_gold(args, settings) -> None:
    store = _store(settings)
    cases = []
    for p in sorted((EVAL_DIR / "gold_drafts").glob("*.json")):
        cases.extend(json.loads(p.read_text(encoding="utf-8")))
    for c in cases:
        for e in c["evidence"]:
            if not quote_is_valid([t.text for t in store.turns(e["meeting_id"])], e["quote"]):
                sys.exit(f"{c['case_id']}: evidence quote does not verify: {e}")
        c["ambiguous"] = c["case_id"] in AMBIGUOUS
    out = EVAL_DIR / "gold_set.json"
    out.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(cases)} cases, all evidence quotes verified -> {out}")


def _evidence_hit(store: Store, hits, evidence: list[dict]) -> tuple[bool, set[str]]:
    """Does any retrieved chunk contain a turn holding a gold evidence quote?"""
    found, meetings = False, set()
    for e in evidence:
        turns = store.turns(e["meeting_id"])
        nq = normalize(e["quote"])
        idx = next((t.idx for t in turns if nq in normalize(t.text)), None)
        for h in hits:
            if h.meeting_id == e["meeting_id"] and idx is not None and h.start_idx <= idx <= h.end_idx:
                found = True
                meetings.add(e["meeting_id"])
    return found, meetings


def eval_retrieval(args, settings) -> None:
    store = _store(settings)
    cases = json.loads((EVAL_DIR / "gold_set.json").read_text(encoding="utf-8"))
    modes = ["bm25"] + (["dense", "hybrid"] if settings.use_embeddings else [])
    r = Retriever(store, settings.embedding_model if settings.use_embeddings else None)
    if settings.use_embeddings and not r.dense_enabled:
        modes = ["bm25"]
    rows = []
    for k in (5, 10, 20):
        for mode in modes:
            any_hit, ev_cov, mtg_cov = 0, 0.0, 0.0
            t0 = time.monotonic()
            for c in cases:
                hits = r.search_chunks(c["question"], team=c["team"], limit=k, mode=mode)
                found, mets = _evidence_hit(store, hits, c["evidence"])
                any_hit += found
                gold_m = {e["meeting_id"] for e in c["evidence"]}
                mtg_cov += len(mets) / len(gold_m)
                per_ev = sum(_evidence_hit(store, hits, [e])[0] for e in c["evidence"]) / len(c["evidence"])
                ev_cov += per_ev
            n = len(cases)
            rows.append({"k": k, "mode": mode, "any_evidence_hit": round(any_hit / n, 3),
                         "evidence_recall": round(ev_cov / n, 3), "gold_meeting_coverage": round(mtg_cov / n, 3),
                         "ms_per_query": round((time.monotonic() - t0) * 1000 / n, 1)})
    out = {"cases": len(cases), "query": "raw question text, team-scoped", "results": rows}
    path = EVAL_DIR / "results" / "retrieval_eval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for row in rows:
        print(row)


def score_answer(case: dict, answer: str, citations: list[dict], store: Store) -> dict:
    a = " " + answer.lower() + " "
    facts = []
    for f in case["key_facts"]:
        hit = next((m for m in f["match_any"] if m.lower() in a), None)
        facts.append({"fact": f["fact"], "matched": hit})
    valid = [c for c in citations if quote_is_valid([t.text for t in store.turns(c["meeting_id"])], c["quote"])]
    gold_m = {e["meeting_id"] for e in case["evidence"]}
    cited_m = {c["meeting_id"] for c in valid}
    return {
        "fact_recall": round(sum(1 for f in facts if f["matched"]) / len(facts), 3),
        "facts": facts,
        "citations": len(citations),
        "citations_valid": len(valid),
        "cites_gold_meeting": bool(gold_m & cited_m),
        "meetings_cited": sorted(cited_m),
    }


def eval_gold(args, settings) -> None:
    store = _store(settings)
    llm = LLM(settings, store)
    if not llm.available:
        sys.exit("No ANTHROPIC_API_KEY configured.")
    retriever = Retriever(store, settings.embedding_model if settings.use_embeddings else None)
    agent = Agent(settings, store, llm, retriever)
    cases = json.loads((EVAL_DIR / "gold_set.json").read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["case_id"] in set(args.only.split(","))]

    def run(c):
        r = agent.answer(c["question"], team=c["team"])
        s = score_answer(c, r.answer, r.citations, store)
        print(f"{c['case_id']:<12} {r.state:<16} facts={s['fact_recall']:.2f} cites={s['citations_valid']}/{s['citations']} "
              f"steps={r.steps} {r.seconds:.0f}s ${r.usage.cost_usd:.3f}", file=sys.stderr)
        return {"case_id": c["case_id"], "team": c["team"], "category": c["category"], "ambiguous": c.get("ambiguous", False),
                "question": c["question"], "gold_answer": c["answer"], "answer": r.answer, "state": r.state,
                "citations": r.citations, "score": s, "steps": r.steps, "tool_calls": r.tool_calls, "seconds": r.seconds,
                "usage": r.usage.as_dict(), "trace": [t.as_dict() for t in r.trace]}

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(run, cases))
    clean = [x for x in results if not x["ambiguous"]]
    summary = {
        "cases": len(results),
        "mean_fact_recall": round(sum(x["score"]["fact_recall"] for x in results) / len(results), 3),
        "mean_fact_recall_excl_ambiguous": round(sum(x["score"]["fact_recall"] for x in clean) / max(1, len(clean)), 3),
        "all_facts_matched": sum(1 for x in results if x["score"]["fact_recall"] == 1.0),
        "answered": sum(1 for x in results if x["state"] in ("answered", "answered_partial")),
        "citations_valid_rate": round(sum(x["score"]["citations_valid"] for x in results) / max(1, sum(x["score"]["citations"] for x in results)), 3),
        "cites_gold_meeting_rate": round(sum(x["score"]["cites_gold_meeting"] for x in results) / len(results), 3),
        "mean_steps": round(sum(x["steps"] for x in results) / len(results), 2),
        "mean_seconds": round(sum(x["seconds"] for x in results) / len(results), 1),
        "total_cost_usd": round(sum(x["usage"]["cost_usd"] for x in results), 3),
        "model": settings.agent_model, "effort": settings.agent_effort,
    }
    out = EVAL_DIR / "results" / f"gold_eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"-> {out}", file=sys.stderr)


_SENT_RE = re.compile(r"[.!?](\s|$)")


def check_answers(args, settings) -> None:
    store = _store(settings)
    data = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    qs = {}
    if args.questions and Path(args.questions).exists():
        qs = {q["question_id"]: q for q in json.loads(Path(args.questions).read_text(encoding="utf-8"))["questions"]}
    rows, problems = [], 0
    for a in data["answers"]:
        cites = a.get("citations", [])
        checks = []
        for c in cites:
            turns = store.turns(c["meeting_id"])
            team_ok = not qs or c["meeting_id"].startswith(qs.get(a["question_id"], {}).get("team", ""))
            ok = bool(turns) and word_count(c["quote"]) >= MIN_QUOTE_WORDS and quote_is_valid([t.text for t in turns], c["quote"])
            checks.append(ok and team_ok)
        sentences = len(_SENT_RE.findall(a["answer"].strip())) or 1
        row = {"question_id": a["question_id"], "n_citations": len(cites), "valid": sum(checks),
               "format_ok": 1 <= len(cites) <= 3, "sentences": sentences, "meetings": sorted({c["meeting_id"] for c in cites})}
        problems += (not row["format_ok"]) + (row["valid"] < len(cites))
        rows.append(row)
    brief = data.get("brief", "")
    brief_quotes = re.findall(r'\[([A-Z]{2}\d{4}[a-z]): "(.*?)"\]', brief)
    brief_valid = sum(quote_is_valid([t.text for t in store.turns(m)], q) for m, q in brief_quotes)
    summary = {"answers": len(rows), "citations": sum(r["n_citations"] for r in rows), "citations_valid": sum(r["valid"] for r in rows),
               "answers_with_format_problems": sum(not r["format_ok"] for r in rows),
               "answers_over_3_sentences": sum(r["sentences"] > 3 for r in rows),
               "answers_citing_2plus_meetings": sum(len(r["meetings"]) >= 2 for r in rows),
               "brief_citations": len(brief_quotes), "brief_citations_valid": brief_valid, "problems": problems}
    print(json.dumps(summary, indent=2))
    if args.verbose:
        for r in rows:
            print(r)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="meeting_memory.evaluate")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-gold")
    sub.add_parser("retrieval")
    g = sub.add_parser("gold")
    g.add_argument("--only")
    g.add_argument("--concurrency", type=int, default=4)
    c = sub.add_parser("check-answers")
    c.add_argument("--answers", default=str(PROJECT_ROOT / "answers.json"))
    c.add_argument("--questions", default=str(PROJECT_ROOT / "data" / "questions.json"))
    c.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    settings = get_settings()
    {"build-gold": build_gold, "retrieval": eval_retrieval, "gold": eval_gold, "check-answers": check_answers}[args.cmd](args, settings)


if __name__ == "__main__":
    main()
