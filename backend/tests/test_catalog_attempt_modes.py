"""Capability hints follow the existing engines; start remains authoritative."""

import pytest

from app.content.api import available_modes


def test_topic_modes_require_nonempty_supported_size():
    assert available_modes({"question_count": 2}) == ["learning", "exam"]
    for count in (0, 5001):
        assert available_modes({"question_count": count}) == []


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({}, ["learning", "exam"]),
        ({"policy_version": 2}, []),
        ({"selection_policy": "other"}, []),
        ({"question_limit": 1}, ["exam"]),
        ({"question_limit": 3}, []),
        ({"exam_duration_seconds": 86401}, ["learning"]),
        ({"question_count": 0}, []),
    ],
)
def test_definition_modes_follow_selection_and_duration_policy(updates, expected):
    row = {
        "question_count": 2,
        "selection_policy": "ordered_all",
        "policy_version": 1,
        "question_limit": None,
        "exam_duration_seconds": 120,
    } | updates
    assert available_modes(row, definition=True) == expected
