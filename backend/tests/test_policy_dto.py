import pytest
from pydantic import ValidationError

from app.admin.schemas import QuestionBody, SourceBody
from app.core.errors import ApplicationError
from app.identity.policy import MFA_HTTP_PERMISSIONS, ROLE_PERMISSIONS, authorize


@pytest.mark.parametrize("value", [None, "", "  \t"])
def test_optional_metadata_is_normalized_without_fake_values(value):
    body = QuestionBody(
        text="TEST",
        source_id=value,
        source_reference=value,
        source_page=value,
        options=[
            {"code": "A", "text": "A", "is_correct": True},
            {"code": "B", "text": "B", "is_correct": False},
        ],
    )
    assert body.source_id is None and body.source_reference is None and body.source_page is None
    source = SourceBody(slug="test", title="TEST", attribution="TEST", license_reference=value)
    assert source.license_reference is None


def test_optional_metadata_does_not_relax_answer_key_or_staff_fields():
    with pytest.raises(ValidationError):
        QuestionBody(
            text="TEST",
            options=[
                {"code": "A", "text": "A", "is_correct": False},
                {"code": "B", "text": "B", "is_correct": False},
            ],
        )
    with pytest.raises(ValidationError):
        QuestionBody(text="TEST", status="published", options=[])


def test_publication_capabilities_are_planned_but_unimplemented_routes_stay_closed():
    assert "content.publish" in ROLE_PERMISSIONS["content_editor"]
    assert "content.import.publish" in ROLE_PERMISSIONS["admin"]
    assert "content.import.publish" not in ROLE_PERMISSIONS["content_editor"]
    assert "content.publish" not in MFA_HTTP_PERMISSIONS
    for role, permission in (
        ("content_editor", "content.publish"),
        ("admin", "content.import.publish"),
    ):
        with pytest.raises(ApplicationError) as exc:
            authorize({role}, permission, mfa_verified=True)
        assert exc.value.code == "MFA_REQUIRED"
