"""Resolve shared source and native destinations for each invocation."""

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib


@dataclass(slots=True, frozen=True)
class Paths:
    source_dir: Path
    opencode_dir: Path
    pi_dir: Path | None = None
    goose_dir: Path | None = None
    agy_dir: Path | None = None
    agy_cli_dir: Path | None = None
    nomistakes_dir: Path | None = None
    codex_dir: Path | None = None
    claude_home: Path | None = None


    def target(self, name: str) -> Path:
        path = getattr(self, f"{name}_dir")
        if not isinstance(path, Path):
            raise ValueError(f"destination required for {name}")
        return path


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config").expanduser()


def state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state").expanduser() / "agent-config"


def resolve_source(explicit: Path | None) -> Path:
    source = explicit or os.environ.get("AGENT_CONFIG_REPO")
    if source is None:
        pointer = config_home() / "agent-config" / "config.toml"
        if pointer.exists():
            with pointer.open("rb") as file:
                source = tomllib.load(file).get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"source must be a nonempty path in {pointer}")
    if source is None:
        raise ValueError('source checkout is not configured; pass --source /path/to/agent-config or set source in ~/.config/agent-config/config.toml')
    path = Path(source).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"source directory does not exist: {path}; set --source to your configuration checkout")
    return path


def resolve_paths(
    claude_dir: Path | None = None,
    opencode_dir: Path | None = None,
    pi_dir: Path | None = None,
    goose_dir: Path | None = None,
    agy_dir: Path | None = None,
    agy_cli_dir: Path | None = None,
    nomistakes_dir: Path | None = None,
    codex_dir: Path | None = None,
    claude_home: Path | None = None,
) -> Paths:
    home = Path.home()
    config = config_home()
    return Paths(
        source_dir=resolve_source(claude_dir),
        claude_home=(claude_home or home / ".claude").expanduser().absolute(),
        opencode_dir=Path(opencode_dir or os.environ.get("OPENCODE_CONFIG_DIR") or config / "opencode").expanduser().absolute(),
        pi_dir=(pi_dir or home / ".pi" / "agent").expanduser().absolute(),
        goose_dir=(goose_dir or config / "goose").expanduser().absolute(),
        agy_dir=(agy_dir or home / ".gemini" / "config").expanduser().absolute(),
        agy_cli_dir=(agy_cli_dir or home / ".gemini" / "antigravity-cli").expanduser().absolute(),
        nomistakes_dir=(nomistakes_dir or home / ".no-mistakes").expanduser().absolute(),
        codex_dir=Path(codex_dir or os.environ.get("CODEX_HOME") or home / ".codex").expanduser().absolute(),
    )
