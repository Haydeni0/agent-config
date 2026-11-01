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
    codegraph_dir: Path | None = None
    home: Path | None = None
    shared_skills: Path | None = None
    goose_plugin_dir: Path | None = None
    local_bin: Path | None = None
    claude_mcp_json: Path | None = None
    overlay_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.home is None:
            object.__setattr__(self, "home", Path.home())
        if self.claude_home is None:
            object.__setattr__(self, "claude_home", self.home / ".claude")
        if self.shared_skills is None:
            object.__setattr__(self, "shared_skills", self.home / ".agents" / "skills")
        if self.goose_plugin_dir is None:
            object.__setattr__(self, "goose_plugin_dir", self.home / ".agents" / "plugins" / "agent-config-goose")
        if self.local_bin is None:
            object.__setattr__(self, "local_bin", self.home / ".local" / "bin")
        if self.overlay_dir is None:
            object.__setattr__(self, "overlay_dir", config_home() / "agent-config" / "overlays")
        if self.claude_mcp_json is None and self.claude_home is not None:
            profile = os.environ.get("CLAUDE_CONFIG_DIR")
            base = self.claude_home if profile else self.claude_home.parent
            object.__setattr__(self, "claude_mcp_json", base / ".claude.json")

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
    codegraph_dir: Path | None = None,
) -> Paths:
    home = Path.home()
    config = config_home()
    claude_profile = os.environ.get("CLAUDE_CONFIG_DIR")
    pi_agent_dir = os.environ.get("PI_CODING_AGENT_DIR")
    return Paths(
        source_dir=resolve_source(claude_dir),
        home=home,
        claude_home=(claude_home or (Path(claude_profile) if claude_profile else None) or home / ".claude").expanduser().absolute(),
        opencode_dir=Path(opencode_dir or os.environ.get("OPENCODE_CONFIG_DIR") or config / "opencode").expanduser().absolute(),
        pi_dir=(pi_dir or (Path(pi_agent_dir) if pi_agent_dir else None) or home / ".pi" / "agent").expanduser().absolute(),
        goose_dir=(goose_dir or config / "goose").expanduser().absolute(),
        agy_dir=(agy_dir or home / ".gemini" / "config").expanduser().absolute(),
        agy_cli_dir=(agy_cli_dir or home / ".gemini" / "antigravity-cli").expanduser().absolute(),
        nomistakes_dir=(nomistakes_dir or home / ".no-mistakes").expanduser().absolute(),
        codex_dir=Path(codex_dir or os.environ.get("CODEX_HOME") or home / ".codex").expanduser().absolute(),
        codegraph_dir=(codegraph_dir or home / ".codegraph").expanduser().absolute(),
    )
