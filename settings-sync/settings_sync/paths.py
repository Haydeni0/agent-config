"""Resolve shared source and native destinations for each invocation."""

from dataclasses import dataclass, fields
import os
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Paths:
    source_dir: Path
    opencode_dir: Path | None = None
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
        if self.opencode_dir is None:
            object.__setattr__(self, "opencode_dir", config_home() / "opencode")
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
    harnesses: "tuple[Harness, ...]",
    claude_dir: Path | None = None,
    **destinations: Path | None,
) -> Paths:
    from settings_sync.registry import Harness  # local import keeps the module graph acyclic

    home = Path.home()
    config = config_home()
    known = {dest.attr for harness in harnesses for dest in harness.destinations}
    unknown = set(destinations) - known
    if unknown:
        raise ValueError(f"unknown destination override: {', '.join(sorted(unknown))}")
    resolved: dict[str, Path] = {}
    for harness in harnesses:
        for dest in harness.destinations:
            if dest.attr in resolved:
                continue
            value = destinations.get(dest.attr)
            if value is None and dest.env is not None:
                # An exported-but-empty var counts as unset: Path("") would
                # resolve the destination to the current working directory.
                env_value = os.environ.get(dest.env)
                if env_value:
                    value = Path(env_value)
            if value is None:
                value = dest.default(home, config)
            resolved[dest.attr] = Path(value).expanduser().absolute()
    declared_fields = {f.name for f in fields(Paths)}
    paths = Paths(source_dir=resolve_source(claude_dir), home=home,
                  **{attr: value for attr, value in resolved.items() if attr in declared_fields})
    for attr, value in resolved.items():
        if attr not in declared_fields:
            # A test-only or future declaration's destination: attach it dynamically.
            object.__setattr__(paths, attr, value)
    return paths
