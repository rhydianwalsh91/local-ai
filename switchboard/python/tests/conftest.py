import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Each test starts in local with only the bundled jobs.toml, whatever the shell or .env says."""
    monkeypatch.setenv("AI_ENV", "local")
    monkeypatch.delenv("SWITCHBOARD_CONFIG", raising=False)


@pytest.fixture
def override(tmp_path, monkeypatch):
    """Write a TOML override file and point SWITCHBOARD_CONFIG at it."""

    def write(text: str):
        path = tmp_path / "override.toml"
        path.write_text(text)
        monkeypatch.setenv("SWITCHBOARD_CONFIG", str(path))
        return path

    return write
