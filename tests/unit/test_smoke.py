from engine import project_name
import app


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
