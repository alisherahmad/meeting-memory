from meeting_memory.memory import compute_state, render_prior_state


def item(iid, ordinal, seq, kind, thread="T1", relation="new", related=(), statement="", owner=""):
    return {"item_id": iid, "team": "ZZ0001", "meeting_id": f"ZZ0001{'abcd'[ordinal - 1]}", "ordinal": ordinal, "seq": seq,
            "kind": kind, "thread_id": thread, "relation": relation, "related": list(related), "topic": "energy source",
            "statement": statement or iid, "speakers": [], "owner": owner, "value": "", "evidence": [], "verified": True}


def statuses(threads):
    return {s.item["item_id"]: s.status for ts in threads.values() for s in ts.items}


def test_later_decision_replaces_earlier():
    items = [item("a1", 1, 0, "decision"), item("c1", 3, 0, "decision", relation="replaces", related=["a1"])]
    st = statuses(compute_state(items))
    assert st == {"a1": "superseded", "c1": "current"}


def test_implicit_replace_targets_current_decision_in_thread():
    items = [item("a1", 1, 0, "decision"), item("b1", 2, 0, "decision", relation="replaces")]
    assert statuses(compute_state(items)) == {"a1": "superseded", "b1": "current"}


def test_as_of_replays_history():
    items = [item("a1", 1, 0, "decision"), item("c1", 3, 0, "decision", relation="replaces", related=["a1"])]
    st = statuses(compute_state(items, as_of_ordinal=2))
    assert st == {"a1": "current"}  # meeting c is not visible yet


def test_forward_links_are_ignored():
    # An earlier item cannot change the status of a later one.
    items = [item("a1", 1, 0, "decision", relation="replaces", related=["c1"]), item("c1", 3, 0, "decision")]
    assert statuses(compute_state(items)) == {"a1": "current", "c1": "current"}


def test_action_item_fulfilled_and_open():
    items = [item("a1", 1, 0, "action_item", thread="T2", owner="B"), item("a2", 1, 1, "action_item", thread="T3"),
             item("b1", 2, 0, "report", thread="T2", relation="fulfils", related=["a1"])]
    st = statuses(compute_state(items))
    assert st["a1"] == "done" and st["a2"] == "open"


def test_disagreement_resolved_by_later_decision_is_marked_inferred():
    items = [item("a1", 1, 0, "disagreement"), item("b1", 2, 0, "decision")]
    ts = compute_state(items)["T1"]
    d = next(s for s in ts.items if s.item["item_id"] == "a1")
    assert d.status == "resolved" and d.inferred and d.by == ["b1"]


def test_cancel_and_proposal_adoption():
    items = [item("a1", 1, 0, "proposal"), item("a2", 1, 1, "decision", relation="adopts", related=["a1"]),
             item("b1", 2, 0, "decision", relation="cancels", related=["a2"])]
    st = statuses(compute_state(items))
    assert st == {"a1": "adopted", "a2": "cancelled", "b1": "current"}


def test_render_prior_state_mentions_ids_and_status():
    items = [item("a1", 1, 0, "decision", statement="Use solar cells")]
    text = render_prior_state(compute_state(items))
    assert "THREAD T1" in text and "a1 [decision, current] Use solar cells" in text
    assert render_prior_state({}) .startswith("(no earlier")


def test_reopen_by_decision_supersedes_but_by_question_only_reopens():
    items = [item("b1", 2, 0, "decision"), item("c1", 3, 0, "decision", relation="reopens", related=["b1"])]
    assert statuses(compute_state(items)) == {"b1": "superseded", "c1": "current"}
    items = [item("b1", 2, 0, "decision"), item("c1", 3, 0, "question", relation="reopens", related=["b1"])]
    assert statuses(compute_state(items))["b1"] == "reopened"
