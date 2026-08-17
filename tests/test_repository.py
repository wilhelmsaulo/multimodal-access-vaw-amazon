from pathlib import Path
import yaml


def test_required_project_files_exist():
    required = [
        Path("README.md"),
        Path("environment.yml"),
        Path("config/scenarios.yml"),
        Path("docs/project_scope.md"),
        Path("docs/data_inventory.md"),
    ]
    assert all(path.exists() for path in required)


def test_scenarios_have_draft_status():
    with Path("config/scenarios.yml").open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    assert config["schema_version"] == 1
    assert config["status"] == "draft"
    assert config["modes"]["air"]["enabled"] is False
