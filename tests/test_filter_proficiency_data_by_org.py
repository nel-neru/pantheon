from __future__ import annotations

from main import _filter_proficiency_data_by_org


def test_filter_returns_all_when_store_has_no_org_signal():
    # Flat {agent_id: {skill: record}} store with no org info and plain agent ids:
    # the store is not org-aware, so every agent is returned unchanged.
    data = {
        "reviewer": {"code_review": {"proficiency": 42.0}},
        "explorer": {"indexing": {"proficiency": 10.0}},
    }
    assert _filter_proficiency_data_by_org(data, "MyApp") == data


def test_filter_keeps_only_org_prefixed_agents_when_org_aware():
    # When agent ids are org-namespaced, only the requested org's agents survive.
    data = {
        "MyApp:reviewer": {"code_review": {"proficiency": 42.0}},
        "OtherApp:reviewer": {"code_review": {"proficiency": 7.0}},
    }
    result = _filter_proficiency_data_by_org(data, "MyApp")
    assert set(result) == {"MyApp:reviewer"}


def test_filter_matches_org_prefix_case_insensitively():
    data = {"myapp/reviewer": {"code_review": {"proficiency": 42.0}}}
    result = _filter_proficiency_data_by_org(data, "MyApp")
    assert set(result) == {"myapp/reviewer"}


def test_filter_matches_record_level_org_name():
    data = {
        "reviewer": {"code_review": {"proficiency": 42.0, "org_name": "MyApp"}},
        "other": {"code_review": {"proficiency": 7.0, "org_name": "OtherApp"}},
    }
    result = _filter_proficiency_data_by_org(data, "MyApp")
    assert set(result) == {"reviewer"}
