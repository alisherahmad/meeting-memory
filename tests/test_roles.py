from meeting_memory.chunking import chunk_meeting
from meeting_memory.roles import merge_roles, name_mentions, resolve_team_roles, team_name_roles
from meeting_memory.store import Store
from meeting_memory.transcripts import parse_transcript

C_MEETING = """Meeting: QQ0001c
Team: QQ0001

00:00:01 Speaker B
Let's start. Matthew, can you show the interface?

00:00:05 Speaker C
Sure, here is the interface design with big buttons.

00:00:09 Speaker D
And I looked at the components and the chip.
"""

# Meeting d: letters C and D have swapped people. C now speaks to Matthew; D speaks to Mael.
D_MEETING = """Meeting: QQ0001d
Team: QQ0001

00:00:01 Speaker B
Welcome back everyone.

00:00:04 Speaker C
The basic one costs eight euros. Right, Matthew?

00:00:08 Speaker D
Yes. What do you say, Mael? Is the battery fine?

00:00:12 Speaker A
From a marketing point of view it is fine.
"""


def _store():
    s = Store(":memory:")
    for text in (C_MEETING, D_MEETING):
        m = parse_transcript(text)
        s.upsert_meeting(m, chunk_meeting(m))
    roles_c = [{"speaker": "A", "role": "Marketing Expert", "name": "Anna"},
               {"speaker": "B", "role": "Project Manager", "name": ""},
               {"speaker": "C", "role": "User Interface Designer", "name": "Matthew"},
               {"speaker": "D", "role": "Industrial Designer", "name": ""}]
    s.set_roles("QQ0001", "QQ0001c", "llm", roles_c)
    s.set_roles("QQ0001", "QQ0001d", "llm", roles_c)  # the model carried c's mapping into d
    return s


def test_team_name_roles_majority():
    rows = [{"name": "Matthew", "role": "User Interface Designer", "source": "llm"}] * 2 + \
           [{"name": "Matthew", "role": "Industrial Designer", "source": "llm"},
            {"name": "", "role": "Project Manager", "source": "llm"}]
    assert team_name_roles(rows) == {"Matthew": "User Interface Designer"}


def test_only_direct_address_counts_not_self_reference():
    # Self-references seen in the corpus ("me again, Rajan the Marketing Expert",
    # "Paul Wiezer. Paul Wiezer.") must not count; only direct address does.
    m = parse_transcript("Meeting: QQ0001a\nTeam: QQ0001\n\n"
                         "00:00:01 Speaker C\nHi, I'm Matthew, the designer. Matthew Smith.\n\n"
                         "00:00:03 Speaker B\nMe again, Matthew the designer, as Matthew said.\n\n"
                         "00:00:05 Speaker A\nThanks, Matthew. Right, Matthew?\n\n"
                         "00:00:07 Speaker D\nSo Paul, you can go next.\n")
    assert dict(name_mentions(m.turns, ["Matthew", "Paul"])) == {"A": {"Matthew"}, "D": {"Paul"}}


def test_swap_is_resolved_and_untouched_meeting_kept():
    s = _store()
    changes = resolve_team_roles(s, "QQ0001")
    assert list(changes) == ["QQ0001d"]  # meeting c had no conflicting mention
    roles = merge_roles([dict(r) for r in s.roles("QQ0001")])
    assert roles["QQ0001d"]["C"]["role"] == "Industrial Designer"
    assert roles["QQ0001d"]["D"]["role"] == "User Interface Designer"
    assert roles["QQ0001d"]["D"]["name"] == "Matthew" and roles["QQ0001d"]["C"]["name"] == ""
    assert roles["QQ0001d"]["A"]["role"] == "Marketing Expert" and roles["QQ0001d"]["B"]["role"] == "Project Manager"
    assert roles["QQ0001c"]["C"]["role"] == "User Interface Designer"
    # Idempotent: a second run reaches the same result.
    assert resolve_team_roles(s, "QQ0001") == changes
