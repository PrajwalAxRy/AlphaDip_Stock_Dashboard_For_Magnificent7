import pytest

from engine import project_name
import app

pytestmark = pytest.mark.unit


def test_project_name_smoke() -> None:
    assert project_name() == "AlphaDip 2026"


def test_missing_secrets_fallback_non_crashing(monkeypatch) -> None:
    class FakeStreamlit:
        @property
        def secrets(self):
            raise RuntimeError("secrets missing")

    monkeypatch.setattr(app, "st", FakeStreamlit())
    required = ["FMP_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
    assert app.get_missing_secrets(required) == required


def test_get_missing_secrets_marks_blank_values_as_missing(monkeypatch) -> None:
    class FakeStreamlit:
        secrets = {
            "FMP_API_KEY": "   ",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "service-role-key",
        }

    monkeypatch.setattr(app, "st", FakeStreamlit())
    required = ["FMP_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
    assert app.get_missing_secrets(required) == ["FMP_API_KEY"]
