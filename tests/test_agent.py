from conftest import FakeBackend, message, text_block, tool_use
from meeting_memory.agent import STATE_ANSWERED, STATE_BUDGET, STATE_FAILED, STATE_PARTIAL, Agent
from meeting_memory.llm import LLM, LLMError
from meeting_memory.retrieval import Retriever

GOOD_QUOTE = {"meeting_id": "ZZ0001b", "turn": 3, "quote": "we drop the solar cells and use a rechargeable battery"}
BAD_QUOTE = {"meeting_id": "ZZ0001b", "turn": 3, "quote": "we unanimously chose a nuclear reactor for power"}
EARLIER = {"meeting_id": "ZZ0001a", "turn": 3, "quote": "for now we go with solar cells as the energy source"}


def make_agent(settings, store, responses):
    backend = FakeBackend(responses)
    return Agent(settings, store, LLM(settings, store, backend=backend), Retriever(store, None)), backend


def submit(cites, id_="s1", answer="They switched to a rechargeable battery."):
    return message([tool_use("submit_answer", {"answer": answer, "citations": cites}, id_)])


def test_search_then_verified_answer(settings, store):
    agent, backend = make_agent(settings, store, [
        message([tool_use("search_transcripts", {"query": "energy source battery", "team": "ZZ0001"}, "t1"),
                 tool_use("list_meetings", {"team": "ZZ0001"}, "t2")]),
        submit([GOOD_QUOTE, {"meeting_id": "ZZ0001a", "quote": "FOR NOW we go with  solar cells as the energy source"}]),
    ])
    res = agent.answer("What energy source did Team ZZ0001 end with?")
    assert res.state == STATE_ANSWERED and res.team == "ZZ0001" and res.steps == 2 and res.tool_calls == 2
    assert [c["meeting_id"] for c in res.citations] == ["ZZ0001b", "ZZ0001a"]
    assert res.citations[1]["quote"] == "for now we go with solar cells as the energy source"  # exact transcript casing
    # Both tool results went back in ONE user message, with matching ids.
    second = backend.requests[1]["messages"]
    assert [b["tool_use_id"] for b in second[-1]["content"]] == ["t1", "t2"]


def test_bad_quote_is_rejected_then_fixed(settings, store):
    agent, backend = make_agent(settings, store, [submit([BAD_QUOTE], "s1"), submit([GOOD_QUOTE, EARLIER], "s2")])
    res = agent.answer("Team ZZ0001 energy?")
    assert res.state == STATE_ANSWERED and res.steps == 2
    feedback = backend.requests[1]["messages"][-1]["content"][0]
    assert feedback["is_error"] and "not found verbatim" in feedback["content"]
    assert any(e.kind == "submit_rejected" for e in res.trace)


def test_partial_after_repeated_rejections_keeps_only_verified(settings, store):
    agent, _ = make_agent(settings, store, [submit([GOOD_QUOTE, BAD_QUOTE], "s1"), submit([GOOD_QUOTE, BAD_QUOTE], "s2")])
    res = agent.answer("Team ZZ0001 energy?")
    assert res.state == STATE_PARTIAL and len(res.citations) == 1 and "dropped" in res.error


def test_budget_exhausted_when_model_never_submits(settings, store):
    loop = [message([tool_use("read_turns", {"meeting_id": "ZZ0001a", "start": 0, "end": i}, f"r{i}")]) for i in range(10)]
    agent, backend = make_agent(settings, store, loop)
    res = agent.answer("Team ZZ0001 anything?")
    assert res.state == STATE_BUDGET and res.steps == settings.max_agent_steps
    last_user = backend.requests[-1]["messages"][-1]["content"]
    assert any(b.get("type") == "text" and "submit_answer now" in b["text"] for b in last_user)


def test_duplicate_calls_are_served_from_cache_and_bad_args_rejected(settings, store):
    same = {"meeting_id": "ZZ0001a", "start": 0, "end": 1}
    agent, backend = make_agent(settings, store, [
        message([tool_use("read_turns", same, "a1")]),
        message([tool_use("read_turns", same, "a2"), tool_use("read_turns", {"meeting_id": "../etc/passwd", "start": 0, "end": 1}, "a3")]),
        submit([GOOD_QUOTE, EARLIER]),
    ])
    res = agent.answer("Team ZZ0001?")
    assert res.state == STATE_ANSWERED
    results = backend.requests[2]["messages"][-1]["content"]
    assert results[0]["content"].startswith("(Duplicate call")
    assert results[1]["is_error"] and "Invalid arguments" in results[1]["content"]


def test_citation_from_other_team_is_rejected(settings, store):
    agent, backend = make_agent(settings, store, [
        submit([{"meeting_id": "QQ0002a", "quote": "one two three four five six seven"}], "s1"), submit([GOOD_QUOTE, EARLIER], "s2")])
    res = agent.answer("Team ZZ0001?")
    assert res.state == STATE_ANSWERED
    assert "not a meeting of team ZZ0001" in backend.requests[1]["messages"][-1]["content"][0]["content"]


def test_provider_failure_is_a_terminal_state(settings, store):
    agent, _ = make_agent(settings, store, [LLMError("Network error reaching the API", retryable=True)])
    res = agent.answer("Team ZZ0001?")
    assert res.state == STATE_FAILED and "Network" in res.error


def test_prose_without_tool_call_gets_nudged(settings, store):
    agent, backend = make_agent(settings, store, [message([text_block("The answer is battery.")], stop="end_turn"), submit([GOOD_QUOTE, EARLIER])])
    res = agent.answer("Team ZZ0001?")
    assert res.state == STATE_ANSWERED and "submit_answer" in backend.requests[1]["messages"][-1]["content"]


def test_refusal_is_terminal(settings, store):
    agent, _ = make_agent(settings, store, [message([], stop="refusal")])
    assert agent.answer("Team ZZ0001?").state == STATE_FAILED


def test_tool_surface_is_read_only():
    from meeting_memory.tools import TOOL_DEFS

    names = {t["name"] for t in TOOL_DEFS}
    assert names == {"list_meetings", "search_memory", "get_thread", "search_transcripts", "read_turns", "submit_answer"}


def test_format_feedback_once_then_accept(settings, store):
    long = "One. Two. Three. Four, and the memory index says so."
    agent, backend = make_agent(settings, store, [submit([GOOD_QUOTE], "s1", answer=long),
                                                  submit([GOOD_QUOTE, EARLIER], "s2", answer="They moved from solar cells to a battery.")])
    res = agent.answer("Team ZZ0001 energy?")
    fb = backend.requests[1]["messages"][-1]["content"][0]["content"]
    assert res.state == STATE_ANSWERED and res.answer.startswith("They moved")
    assert "4 sentences" in fb and "mentions the system" in fb and "one meeting" in fb


def test_format_feedback_is_given_only_once(settings, store):
    agent, _ = make_agent(settings, store, [submit([GOOD_QUOTE], "s1"), submit([GOOD_QUOTE], "s2")])
    res = agent.answer("Team ZZ0001 energy?")
    assert res.state == STATE_ANSWERED and res.steps == 2  # single-meeting answer accepted on resubmission


def test_count_sentences_ignores_decimals():
    from meeting_memory.agent import count_sentences

    assert count_sentences("It cost 12.50 EUR. Then 11.60 EUR.") == 2


def test_truncated_tool_call_is_not_executed(settings, store):
    agent, backend = make_agent(settings, store, [
        message([tool_use("submit_answer", {}, "cut")], stop="max_tokens"),
        submit([GOOD_QUOTE, EARLIER], "s2"),
    ])
    res = agent.answer("Team ZZ0001 energy?")
    assert res.state == STATE_ANSWERED
    fb = backend.requests[1]["messages"][-1]["content"][0]
    assert fb["is_error"] and "cut off" in fb["content"]


def test_invalid_submission_names_the_missing_field(settings, store):
    agent, backend = make_agent(settings, store, [
        message([tool_use("submit_answer", {"answer": "x", "citations": [{"meeting_id": "ZZ0001b"}]}, "s1")]),
        submit([GOOD_QUOTE, EARLIER], "s2"),
    ])
    agent.answer("Team ZZ0001 energy?")
    assert "citations.0.quote: Field required" in backend.requests[1]["messages"][-1]["content"][0]["content"]


def test_sentence_limit_is_enforced_after_two_corrections(settings, store):
    long = "One is here. Two is here. Three is here. Four is here."
    agent, _ = make_agent(settings, store, [submit([GOOD_QUOTE, EARLIER], f"s{i}", answer=long) for i in range(3)])
    res = agent.answer("Team ZZ0001 energy?")
    assert res.state == STATE_ANSWERED and res.answer == "One is here. Two is here. Three is here."
    assert "cut from 4 to 3" in res.error and res.steps == 3
