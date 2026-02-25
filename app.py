from __future__ import annotations

from typing import List

import streamlit as st


REQUIRED_SECRETS = ["FMP_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]


def get_missing_secrets(required_keys: List[str]) -> List[str]:
    try:
        secrets = st.secrets
    except Exception:
        return required_keys

    missing = []
    for key in required_keys:
        value = secrets.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
    return missing


def main() -> None:
    st.set_page_config(page_title="AlphaDip 2026", layout="wide")
    st.title("AlphaDip 2026")
    st.caption("Milestone 1 baseline shell")

    missing = get_missing_secrets(REQUIRED_SECRETS)
    if missing:
        st.error(
            "Missing required Streamlit secrets: "
            + ", ".join(missing)
            + ". Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill values."
        )
    else:
        st.success("Configuration loaded. Ready for next milestones.")

    st.write("Trigger → Monitor → Confirm")


if __name__ == "__main__":
    main()
