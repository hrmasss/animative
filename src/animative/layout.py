"""Where a video project's and a character's files live. Roots come from `config.py`.

A project sits under `<workspace>/projects/<slug>/`.

    projects/<slug>/
        episode/            authored: episode.json, beats/*.md, edit.json,
                            facts.json, generated.json, approvals/, credits.md
        assets/             gathered: sources/, voice/takes/, sound/, generated/,
                            data/, inbox/ (files a person or a browser dropped in)
        build/draft/        composed pages, per-shot renders, timing, the mix
        build/final/        the same for the 1080p final
        videos/<slug>-draft.mp4, videos/<slug>.mp4
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from animative import config


class Episode:
    """One animative project, by slug."""

    def __init__(self, slug: str, final: bool = False):
        self.slug = config.slugify(slug)
        self.final = final
        self.root = config.projects_dir() / self.slug
        self.dir = self.root / "episode"
        self.assets = self.root / "assets"
        self.out = self.root / "build" / ("final" if final else "draft")
        self.hf = self.out / "hf"
        self.videos = self.root / "videos"

    # -- authored ---------------------------------------------------------
    @property
    def episode_json(self) -> Path:
        return self.dir / "episode.json"

    def load(self, name: str) -> dict:
        """An authored JSON file from episode/, or {} when it does not exist yet."""
        p = self.dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    @property
    def character(self) -> str:
        """The character this episode's presenter shots use."""
        ep = self.load("episode.json")
        return ep.get("character") or (ep.get("entities") or ["host"])[0]

    # -- gathered ---------------------------------------------------------
    @property
    def takes(self) -> Path:
        return self.assets / "voice" / "takes"

    @property
    def inbox(self) -> Path:
        return self.assets / "inbox"

    # -- derived ----------------------------------------------------------
    def video(self) -> Path:
        return self.videos / (f"{self.slug}.mp4" if self.final else f"{self.slug}-draft.mp4")

    def exists(self) -> bool:
        return self.episode_json.exists()


def character_dir(name: str) -> Path:
    """A character's authored sheets and rig.json."""
    return config.characters_dir() / name


def character_inputs_hash(name: str) -> str:
    """A fingerprint of what a cut is made from: the rig and every sheet it names.

    The rig is hashed as parsed JSON, not as bytes, so a checkout that rewrites line
    endings (git on Windows) does not make a bundled cut look stale.
    """
    d = character_dir(name)
    rigj = json.loads((d / "rig.json").read_text(encoding="utf-8"))
    h = hashlib.sha256(json.dumps(rigj, sort_keys=True, separators=(",", ":")).encode())
    for key in sorted(rigj["sources"]):
        h.update(key.encode())
        h.update((d / rigj["sources"][key]).read_bytes())
    return h.hexdigest()


def bundled_cut_dir(name: str) -> Path:
    """Where a character keeps its parts ready to use: characters/<name>/parts/."""
    return character_dir(name) / "parts"


def bundle_is_fresh(name: str) -> bool:
    lock = bundled_cut_dir(name) / "rig.lock.json"
    if not lock.exists():
        return False
    return json.loads(lock.read_text(encoding="utf-8")).get("inputs_hash") == character_inputs_hash(name)


def character_cut_dir(name: str) -> Path:
    """A character's cut parts and rig.lock.json.

    The bundled parts when they match the current rig and sheets, so a fresh clone
    works from minute 0 with no cutting. Otherwise the cache, which `animative cut`
    fills: editing a rig or swapping a sheet is picked up without touching the bundle.
    """
    if bundle_is_fresh(name):
        return bundled_cut_dir(name)
    return config.cache_dir() / "characters" / name


def ensure_cut(name: str) -> Path:
    """The cut folder for a character: the bundled parts if current, else a current cache cut.

    Only an out-of-date character loads the cutter (and scipy), so building a video with
    a bundled host needs neither.
    """
    out = character_cut_dir(name)
    lock = out / "rig.lock.json"
    current = lock.exists() and json.loads(lock.read_text(encoding="utf-8")).get(
        "inputs_hash") == character_inputs_hash(name)
    if not current:
        from animative import rig
        rig.cut(name)
        out = character_cut_dir(name)
    return out


def list_characters() -> list[str]:
    root = config.characters_dir()
    return sorted(d.name for d in root.iterdir()
                  if (d / "rig.json").exists() and not d.name.startswith("_")) if root.is_dir() else []


def kit_dir() -> Path:
    """The HyperFrames kit as installed: node_modules beside its package.json (`animative setup`)."""
    return config.kit_install_dir()


def list_episodes() -> list[Episode]:
    root = config.projects_dir()
    if not root.is_dir():
        return []
    return [Episode(d.name) for d in sorted(root.iterdir()) if (d / "episode" / "episode.json").exists()]
