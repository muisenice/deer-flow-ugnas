from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy.sh"
BASH_CANDIDATES = [
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(which("bash")) if which("bash") else None,
]
BASH_EXECUTABLE = next(
    (str(path) for path in BASH_CANDIDATES if path is not None and path.exists() and "WindowsApps" not in str(path)),
    None,
)

if BASH_EXECUTABLE is None:
    pytestmark = pytest.mark.skip(reason="bash is required for deploy.sh tests")


def _run_seed_command(tmp_path: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    source_path = tmp_path / "template.example"
    source_path.write_text("seeded-value\n", encoding="utf-8")

    command = (
        f"source '{SCRIPT_PATH}' && "
        f"seed_file_if_missing '{source_path}' '{destination}' 'template.example'"
    )

    return subprocess.run(
        [BASH_EXECUTABLE, "-lc", command],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_seed_file_if_missing_copies_template_into_missing_destination(tmp_path: Path):
    destination = tmp_path / "config.yaml"

    result = _run_seed_command(tmp_path, destination)

    assert result.returncode == 0
    assert destination.read_text(encoding="utf-8") == "seeded-value\n"


def test_seed_file_if_missing_does_not_overwrite_existing_destination(tmp_path: Path):
    destination = tmp_path / ".env"
    destination.write_text("keep-me\n", encoding="utf-8")

    result = _run_seed_command(tmp_path, destination)

    assert result.returncode == 0
    assert destination.read_text(encoding="utf-8") == "keep-me\n"


def test_seed_file_if_missing_creates_parent_directories_for_nested_destination(tmp_path: Path):
    destination = tmp_path / "frontend" / "nested" / ".env"

    result = _run_seed_command(tmp_path, destination)

    assert result.returncode == 0
    assert destination.read_text(encoding="utf-8") == "seeded-value\n"


def test_sourcing_deploy_script_does_not_enable_errexit_for_caller():
    command = (
        "set +e; "
        f"source '{SCRIPT_PATH}'; "
        "case $- in "
        "*e*) echo 'errexit-on';; "
        "*) echo 'errexit-off';; "
        "esac; "
        "false; "
        "echo 'shell-still-running'"
    )

    result = subprocess.run(
        [BASH_EXECUTABLE, "-lc", command],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "errexit-off" in result.stdout
    assert "shell-still-running" in result.stdout


def test_init_runtime_paths_sets_default_cli_config_directories_under_deer_flow_home(tmp_path: Path):
    deer_flow_home = tmp_path / "runtime-home"
    command = (
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"source '{SCRIPT_PATH}'; "
        "init_runtime_paths; "
        "printf '%s\\n%s\\n' "
        "\"$DEER_FLOW_CLAUDE_CONFIG_DIR\" "
        "\"$DEER_FLOW_CODEX_CONFIG_DIR\""
    )

    result = subprocess.run(
        [BASH_EXECUTABLE, "-lc", command],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if not line.startswith("\x1b")]
    assert [Path(line) for line in lines[-2:]] == [
        deer_flow_home / "cli-config" / ".claude",
        deer_flow_home / "cli-config" / ".codex",
    ]
    assert (deer_flow_home / "cli-config" / ".claude").is_dir()
    assert (deer_flow_home / "cli-config" / ".codex").is_dir()
