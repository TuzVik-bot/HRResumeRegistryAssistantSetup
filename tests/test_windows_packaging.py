from pathlib import Path


def test_windows_spec_uses_windowed_mode():
    spec_path = Path(__file__).resolve().parent.parent / "packaging" / "HRResumeRegistryAssistant.spec"
    content = spec_path.read_text(encoding="utf-8")
    assert "console=False" in content
