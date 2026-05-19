from pathlib import Path


def test_windows_spec_uses_windowed_mode():
    spec_path = Path(__file__).resolve().parent.parent / "packaging" / "HRResumeRegistryAssistant.spec"
    content = spec_path.read_text(encoding="utf-8")
    assert "console=False" in content


def test_windows_spec_includes_templates_and_static_assets():
    spec_path = Path(__file__).resolve().parent.parent / "packaging" / "HRResumeRegistryAssistant.spec"
    content = spec_path.read_text(encoding="utf-8")
    assert '("..\\\\templates", "templates")' in content
    assert '("..\\\\static", "static")' in content


def test_windows_workflow_publishes_release_asset():
    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "windows-installer.yml"
    content = workflow_path.read_text(encoding="utf-8")
    assert "contents: write" in content
    assert "Publish GitHub release installer" in content
    assert "gh release upload" in content
    assert "HRResumeRegistryAssistantSetup.exe" in content
