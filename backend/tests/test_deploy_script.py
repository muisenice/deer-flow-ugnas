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


def _run_bash(command: str) -> subprocess.CompletedProcess[str]:
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

    result = _run_bash(command)

    assert result.returncode == 0
    assert "errexit-off" in result.stdout
    assert "shell-still-running" in result.stdout


def test_init_runtime_paths_sets_default_cli_config_directories_under_deer_flow_home(tmp_path: Path):
    deer_flow_home = tmp_path / "runtime-home"
    host_home = tmp_path / "host-home"
    host_home.mkdir()
    command = (
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"export HOME='{host_home}'; "
        f"source '{SCRIPT_PATH}'; "
        "init_runtime_paths; "
        "printf '%s\\n%s\\n' "
        "\"$DEER_FLOW_CLAUDE_CONFIG_DIR\" "
        "\"$DEER_FLOW_CODEX_CONFIG_DIR\""
    )

    result = _run_bash(command)

    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if not line.startswith("\x1b")]
    assert [Path(line) for line in lines[-2:]] == [
        deer_flow_home / "cli-config" / ".claude",
        deer_flow_home / "cli-config" / ".codex",
    ]
    assert (deer_flow_home / "cli-config" / ".claude").is_dir()
    assert (deer_flow_home / "cli-config" / ".codex").is_dir()


def test_init_runtime_paths_keeps_deterministic_cli_config_defaults_even_when_home_dirs_exist(tmp_path: Path):
    deer_flow_home = tmp_path / "runtime-home"
    host_home = tmp_path / "host-home"
    (host_home / ".claude").mkdir(parents=True)
    (host_home / ".codex").mkdir(parents=True)
    (host_home / ".claude" / ".credentials.json").write_text('{"token":"claude"}\n', encoding="utf-8")
    (host_home / ".claude" / "tmp.lock").write_text("ignore-me\n", encoding="utf-8")
    (host_home / ".codex" / "auth.json").write_text('{"token":"codex"}\n', encoding="utf-8")
    (host_home / ".codex" / "session.tmp").write_text("ignore-me\n", encoding="utf-8")
    command = (
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"export HOME='{host_home}'; "
        f"source '{SCRIPT_PATH}'; "
        "init_runtime_paths; "
        "printf '%s\\n%s\\n' "
        "\"$DEER_FLOW_CLAUDE_CONFIG_DIR\" "
        "\"$DEER_FLOW_CODEX_CONFIG_DIR\""
    )

    result = _run_bash(command)

    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if not line.startswith("\x1b")]
    assert [Path(line) for line in lines[-2:]] == [
        deer_flow_home / "cli-config" / ".claude",
        deer_flow_home / "cli-config" / ".codex",
    ]
    assert (deer_flow_home / "cli-config" / ".claude").is_dir()
    assert (deer_flow_home / "cli-config" / ".codex").is_dir()
    assert (deer_flow_home / "cli-config" / ".claude" / ".credentials.json").read_text(encoding="utf-8") == '{"token":"claude"}\n'
    assert (deer_flow_home / "cli-config" / ".codex" / "auth.json").read_text(encoding="utf-8") == '{"token":"codex"}\n'
    assert not (deer_flow_home / "cli-config" / ".claude" / "tmp.lock").exists()
    assert not (deer_flow_home / "cli-config" / ".codex" / "session.tmp").exists()


def test_init_runtime_paths_seeds_missing_auth_file_even_if_destination_dir_has_irrelevant_files(tmp_path: Path):
    deer_flow_home = tmp_path / "runtime-home"
    host_home = tmp_path / "host-home"
    (host_home / ".claude").mkdir(parents=True)
    (host_home / ".codex").mkdir(parents=True)
    (host_home / ".claude" / ".credentials.json").write_text('{"token":"claude"}\n', encoding="utf-8")
    (host_home / ".codex" / "auth.json").write_text('{"token":"codex"}\n', encoding="utf-8")
    (deer_flow_home / "cli-config" / ".claude").mkdir(parents=True)
    (deer_flow_home / "cli-config" / ".codex").mkdir(parents=True)
    (deer_flow_home / "cli-config" / ".claude" / "notes.txt").write_text("keep-me\n", encoding="utf-8")
    (deer_flow_home / "cli-config" / ".codex" / "notes.txt").write_text("keep-me\n", encoding="utf-8")
    command = (
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"export HOME='{host_home}'; "
        f"source '{SCRIPT_PATH}'; "
        "init_runtime_paths"
    )

    result = _run_bash(command)

    assert result.returncode == 0
    assert (deer_flow_home / "cli-config" / ".claude" / ".credentials.json").read_text(encoding="utf-8") == '{"token":"claude"}\n'
    assert (deer_flow_home / "cli-config" / ".codex" / "auth.json").read_text(encoding="utf-8") == '{"token":"codex"}\n'
    assert (deer_flow_home / "cli-config" / ".claude" / "notes.txt").read_text(encoding="utf-8") == "keep-me\n"
    assert (deer_flow_home / "cli-config" / ".codex" / "notes.txt").read_text(encoding="utf-8") == "keep-me\n"


def test_init_runtime_paths_does_not_overwrite_existing_default_auth_files(tmp_path: Path):
    deer_flow_home = tmp_path / "runtime-home"
    host_home = tmp_path / "host-home"
    (host_home / ".claude").mkdir(parents=True)
    (host_home / ".codex").mkdir(parents=True)
    (host_home / ".claude" / ".credentials.json").write_text('{"token":"claude-host"}\n', encoding="utf-8")
    (host_home / ".codex" / "auth.json").write_text('{"token":"codex-host"}\n', encoding="utf-8")
    (deer_flow_home / "cli-config" / ".claude").mkdir(parents=True)
    (deer_flow_home / "cli-config" / ".codex").mkdir(parents=True)
    (deer_flow_home / "cli-config" / ".claude" / ".credentials.json").write_text('{"token":"claude-runtime"}\n', encoding="utf-8")
    (deer_flow_home / "cli-config" / ".codex" / "auth.json").write_text('{"token":"codex-runtime"}\n', encoding="utf-8")
    command = (
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"export HOME='{host_home}'; "
        f"source '{SCRIPT_PATH}'; "
        "init_runtime_paths"
    )

    result = _run_bash(command)

    assert result.returncode == 0
    assert (deer_flow_home / "cli-config" / ".claude" / ".credentials.json").read_text(encoding="utf-8") == '{"token":"claude-runtime"}\n'
    assert (deer_flow_home / "cli-config" / ".codex" / "auth.json").read_text(encoding="utf-8") == '{"token":"codex-runtime"}\n'


def test_init_runtime_paths_does_not_seed_host_cli_auth_into_overridden_dirs(tmp_path: Path):
    deer_flow_home = tmp_path / "runtime-home"
    host_home = tmp_path / "host-home"
    custom_claude_dir = tmp_path / "custom" / ".claude"
    custom_codex_dir = tmp_path / "custom" / ".codex"
    (host_home / ".claude").mkdir(parents=True)
    (host_home / ".codex").mkdir(parents=True)
    (host_home / ".claude" / ".credentials.json").write_text('{"token":"claude"}\n', encoding="utf-8")
    (host_home / ".codex" / "auth.json").write_text('{"token":"codex"}\n', encoding="utf-8")
    command = (
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        f"export HOME='{host_home}'; "
        f"export DEER_FLOW_CLAUDE_CONFIG_DIR='{custom_claude_dir}'; "
        f"export DEER_FLOW_CODEX_CONFIG_DIR='{custom_codex_dir}'; "
        f"source '{SCRIPT_PATH}'; "
        "init_runtime_paths"
    )

    result = _run_bash(command)

    assert result.returncode == 0
    assert custom_claude_dir.is_dir()
    assert custom_codex_dir.is_dir()
    assert list(custom_claude_dir.iterdir()) == []
    assert list(custom_codex_dir.iterdir()) == []


def test_ensure_frontend_auth_env_sets_production_defaults():
    command = (
        f"source '{SCRIPT_PATH}'; "
        "unset BETTER_AUTH_URL; "
        "unset DEER_FLOW_TRUSTED_ORIGINS; "
        "unset PORT; "
        "ensure_frontend_auth_env; "
        "printf '%s\\n%s\\n' "
        "\"$BETTER_AUTH_URL\" "
        "\"$DEER_FLOW_TRUSTED_ORIGINS\""
    )

    result = _run_bash(command)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[-2] == "http://localhost:2026"
    assert lines[-1] == "http://localhost:2026,http://127.0.0.1:2026"


def test_ensure_frontend_auth_env_uses_better_auth_url_as_trusted_origin_seed():
    command = (
        f"source '{SCRIPT_PATH}'; "
        "export BETTER_AUTH_URL='http://10.81.172.129:2026'; "
        "unset DEER_FLOW_TRUSTED_ORIGINS; "
        "ensure_frontend_auth_env; "
        "printf '%s\\n%s\\n' "
        "\"$BETTER_AUTH_URL\" "
        "\"$DEER_FLOW_TRUSTED_ORIGINS\""
    )

    result = _run_bash(command)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[-2] == "http://10.81.172.129:2026"
    assert lines[-1] == (
        "http://10.81.172.129:2026,http://localhost:2026,http://127.0.0.1:2026"
    )


def test_ensure_frontend_auth_env_preserves_explicit_trusted_origins():
    command = (
        f"source '{SCRIPT_PATH}'; "
        "export BETTER_AUTH_URL='http://10.81.172.129:2026'; "
        "export DEER_FLOW_TRUSTED_ORIGINS='http://nas.lan:2026,http://10.81.172.129:2026'; "
        "ensure_frontend_auth_env; "
        "printf '%s\\n%s\\n' "
        "\"$BETTER_AUTH_URL\" "
        "\"$DEER_FLOW_TRUSTED_ORIGINS\""
    )

    result = _run_bash(command)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[-2] == "http://10.81.172.129:2026"
    assert lines[-1] == "http://nas.lan:2026,http://10.81.172.129:2026"


def test_main_down_skips_runtime_bootstrap_on_clean_checkout(tmp_path: Path):
    repo_root = tmp_path / "repo"
    frontend_dir = repo_root / "frontend"
    docker_dir = repo_root / "docker"
    deer_flow_home = repo_root / "runtime-home"

    frontend_dir.mkdir(parents=True)
    docker_dir.mkdir()
    (repo_root / "config.example.yaml").write_text("models: []\n", encoding="utf-8")
    (repo_root / ".env.example").write_text("ROOT_ENV=1\n", encoding="utf-8")
    (frontend_dir / ".env.example").write_text("FRONTEND_ENV=1\n", encoding="utf-8")

    command = (
        f"source '{SCRIPT_PATH}'; "
        f"REPO_ROOT='{repo_root}'; "
        "DOCKER_DIR=\"$REPO_ROOT/docker\"; "
        "COMPOSE_CMD=(printf 'compose %s\\n'); "
        f"export DEER_FLOW_HOME='{deer_flow_home}'; "
        "unset DEER_FLOW_CONFIG_PATH; "
        "unset DEER_FLOW_EXTENSIONS_CONFIG_PATH; "
        "main down"
    )

    result = _run_bash(command)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "compose down"
    assert not deer_flow_home.exists()
    assert not (repo_root / ".env").exists()
    assert not (frontend_dir / ".env").exists()
    assert not (repo_root / "config.yaml").exists()
    assert not (repo_root / "extensions_config.json").exists()
