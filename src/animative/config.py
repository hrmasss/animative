"""Where everything lives. The one place that knows.

A **workspace** is any folder `animative init` has been run in; it holds your
characters and your video projects. Commands find it by walking up from the
current directory to the nearest `.animative/` folder, or from
`ANIMATIVE_WORKSPACE`. Your **provider choices** (which tool makes images,
voices, music) are about you, not one workspace, so they live in your user
config folder. The engine's own files (the graphics kit, examples, the
character template) ship inside the package.

    <workspace>/
        .animative/             marker, plus cache/ (cuts, render lock, map data)
        .env                    API keys, e.g. GEMINI_API_KEY (never committed)
        characters/<name>/      a host: sources/, reference.png, rig.json, parts/
        projects/<slug>/        a video: episode/, assets/, build/, videos/
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
KIT_SRC = PACKAGE_DIR / "kit"
EXAMPLES_DIR = PACKAGE_DIR / "examples"
TEMPLATE_CHARACTER = PACKAGE_DIR / "characters" / "_template"
MARKER = ".animative"


def user_config_dir() -> Path:
    if os.environ.get("ANIMATIVE_CONFIG"):
        return Path(os.environ["ANIMATIVE_CONFIG"])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "animative"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "animative"


def user_cache_dir() -> Path:
    if os.environ.get("ANIMATIVE_CACHE"):
        return Path(os.environ["ANIMATIVE_CACHE"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "animative" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "animative"


def choices_file() -> Path:
    """One person's provider choices: image, video, voice, music, effects."""
    return user_config_dir() / "choices.json"


def kit_install_dir() -> Path:
    """Where the kit's Node packages are installed (`animative setup`), one per kit version."""
    import json
    version = json.loads((KIT_SRC / "package.json").read_text(encoding="utf-8"))["dependencies"]["hyperframes"]
    return user_cache_dir() / f"kit-hyperframes-{version}"


def find_workspace(start: Path | None = None) -> Path | None:
    if os.environ.get("ANIMATIVE_WORKSPACE"):
        return Path(os.environ["ANIMATIVE_WORKSPACE"]).resolve()
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / MARKER).is_dir():
            return d
    return None


def workspace() -> Path:
    ws = find_workspace()
    if ws is None:
        raise SystemExit("not inside an animative workspace: run  animative init  in the folder you want to use")
    return ws


def projects_dir() -> Path:
    return workspace() / "projects"


def characters_dir() -> Path:
    return workspace() / "characters"


def cache_dir() -> Path:
    return workspace() / MARKER / "cache"


_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def slugify(name: str) -> str:
    """`My Drone Video` -> `my-drone-video`."""
    s = _SLUG_RE.sub("-", str(name).strip().lower().replace("_", "-"))
    return s.strip("-") or "untitled"


def load_env() -> None:
    """Read the workspace's .env into the environment, without overriding what is already set."""
    ws = find_workspace()
    env = ws / ".env" if ws else None
    if not env or not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
