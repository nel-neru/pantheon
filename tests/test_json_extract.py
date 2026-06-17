"""Cycle 20: canonical LLM-output JSON extraction (core.llm.extract_json_object).

These tests pin the cases the previous ad-hoc brace scans got wrong:
- non-greedy ``re.search(r"\\{.*?\\}")`` truncated at the first ``}`` (nested
  objects / ``}`` inside a string value),
- greedy ``re.search(r"\\{.*\\}")`` over-captured a stray ``}`` in trailing
  prose and then ``json.loads`` raised.
Plus integration coverage through the real goals LLM path (GoalParser /
GoalDecomposer) so the migration is load-bearing, not just the helper in
isolation.
"""

from __future__ import annotations

from core.goals.goal_decomposer import GoalDecomposer
from core.goals.goal_parser import GoalParser, StructuredGoal
from core.llm import extract_json_object


# --------------------------------------------------------------------------- #
# canonical helper                                                             #
# --------------------------------------------------------------------------- #
def test_clean_object():
    assert extract_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_none_and_empty_return_none():
    assert extract_json_object(None) is None
    assert extract_json_object("") is None
    assert extract_json_object("no json at all") is None


def test_leading_prose_then_object():
    assert extract_json_object('Here is the result:\n{"ok": true}') == {"ok": True}


def test_trailing_prose_with_brace_is_ignored():
    # The old greedy regex captured through the stray `}` in the prose and then
    # json.loads raised; raw_decode stops at the end of the first valid value.
    text = '{"ok": true}\nNote: the closing brace } above is intentional.'
    assert extract_json_object(text) == {"ok": True}


def test_nested_object_not_truncated():
    # The old non-greedy regex stopped at the first `}` (after "b"), losing the
    # outer structure. raw_decode parses the whole nested value.
    text = '{"epics": [{"title": "E", "stories": [{"title": "S"}]}]}'
    assert extract_json_object(text) == {"epics": [{"title": "E", "stories": [{"title": "S"}]}]}


def test_brace_inside_string_value_preserved():
    # A `}` inside a string value must not terminate extraction early.
    text = '{"description": "fix the {config} bug }", "scope": "module"}'
    assert extract_json_object(text) == {
        "description": "fix the {config} bug }",
        "scope": "module",
    }


def test_code_fence_json_label():
    text = 'prose\n```json\n{"departments": []}\n```\ntrailing'
    assert extract_json_object(text) == {"departments": []}


def test_code_fence_bare():
    text = '```\n{"x": [1, 2, 3]}\n```'
    assert extract_json_object(text) == {"x": [1, 2, 3]}


def test_malformed_json_returns_none_not_raises():
    assert extract_json_object('{"a": 1, "b":}') is None


# --------------------------------------------------------------------------- #
# integration: real goals LLM path uses the robust extractor                   #
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    """Minimal stand-in for the synchronous ``.invoke(prompt).content`` client."""

    def __init__(self, content: str):
        self._content = content

    def invoke(self, prompt: str):  # noqa: ARG002 - prompt unused by the fake
        return _FakeResponse(self._content)


def test_goal_parser_llm_path_handles_brace_in_string():
    # Flat schema with a `}` inside a value — the old non-greedy regex would
    # truncate here and silently fall back to the heuristic.
    content = (
        "Sure!\n```json\n"
        '{"goal_type": "improvement", "scope": "module", '
        '"description": "tidy the {legacy} module", '
        '"success_criteria": ["c1"], "scale": "small"}\n```'
    )
    parser = GoalParser(llm_client=_FakeLLM(content))
    goal = parser.parse("tidy the legacy module", use_llm=True)
    assert isinstance(goal, StructuredGoal)
    assert goal.description == "tidy the {legacy} module"
    assert goal.scope == "module"


def test_goal_decomposer_llm_path_parses_nested_plan():
    content = (
        "Here is the decomposition:\n"
        '{"epics": [{"title": "Epic A", "description": "d", '
        '"stories": [{"title": "Story A", "tasks": ['
        '{"title": "Task A", "description": "t", '
        '"required_skills": ["deep_research"], "estimated_tokens": 1000, '
        '"depends_on_prev": false}]}]}]}\n'
        # Stray `}` in trailing prose: the OLD greedy regex over-captured to here
        # and json.loads raised; raw_decode stops at the end of the first value.
        "That should cover it (note the closing } here)."
    )
    goal = StructuredGoal(
        goal_id="goal:improvement:x",
        raw_text="x",
        goal_type="improvement",
        scope="repository",
        description="x",
        success_criteria=[],
        constraints=[],
        suggested_categories=[],
    )
    decomposer = GoalDecomposer(llm_client=_FakeLLM(content))
    plan = decomposer.decompose(goal, use_llm=True)
    titles = [e.title for e in plan.epics]
    assert "Epic A" in titles
