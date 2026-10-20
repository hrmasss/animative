"""Bring a file made outside animative into an episode, with a record of how.

Browser and manual providers (AI Studio, ChatGPT, Gemini, Flow, a file someone
made by hand) all end the same way: a file lands somewhere, usually
``projects/<slug>/assets/inbox/``, and this moves it into place beside a sidecar
naming the provider and the prompt. That sidecar is what credits and pins read,
so an imported file is as traceable as one animative generated itself.

    animative import <slug> voice <beat> <file> --via ai-studio-web [--prompt-file p.txt]
    animative import <slug> still <id> <file> --via chatgpt-web
    animative import <slug> clip <id> <file> --via flow-web
    animative import <slug> music bed <file> --via library --license "Pixabay Content License" --page <url>
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from animative import layout, voice

KINDS = ("voice", "still", "clip", "music", "sfx")


def _prompt_for(ep: layout.Episode, kind: str, ident: str) -> str | None:
    """The prompt the episode already holds for this item, so the sidecar can say what was asked."""
    if kind == "voice":
        for b in voice.beats(ep):
            if b["id"] == ident:
                return voice.prompt(b, ep.load("episode.json"))
        raise SystemExit(f"no beat {ident!r} in this episode")
    if kind in ("still", "clip"):
        spec = ep.load("generated.json")
        for s in spec.get("stills", []) + spec.get("clips", []):
            if s["id"] == ident:
                return f"{s['prompt']} {spec.get('rules', '')}".strip()
    return None


def import_file(slug: str, kind: str, ident: str, src: str, via: str, prompt_text: str | None = None,
                license_name: str | None = None, page: str | None = None) -> Path:
    if kind not in KINDS:
        raise SystemExit(f"kind must be one of {', '.join(KINDS)}")
    ep = layout.Episode(slug)
    file = Path(src)
    if not file.exists():
        file = ep.inbox / src
    if not file.exists():
        raise SystemExit(f"no file {src} (looked in the cwd and in {ep.inbox})")
    rec: dict = {"provider": via, "imported_from": file.name,
                 "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                 "prompt": prompt_text or _prompt_for(ep, kind, ident)}
    if kind == "voice":
        ep.takes.mkdir(parents=True, exist_ok=True)
        n = len(list(ep.takes.glob(f"{ident}--*.wav"))) + 1
        dest = ep.takes / f"{ident}--{via}--{n:02d}.wav"
        rec.update({"beat": ident, "voice": via, "model_served": via, "seconds": voice.to_wav(file, dest)})
    elif kind in ("still", "clip"):
        d = ep.assets / "generated" / via
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"{ident}{file.suffix.lower()}"
        shutil.copy2(file, dest)
        rec.update({"id": ident, "tool": via, "use": "illustration only, never evidence"})
    else:
        d = ep.assets / "sound" / ("music" if kind == "music" else "sfx")
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"{ident}{file.suffix.lower()}"
        shutil.copy2(file, dest)
        lic = ep.assets / "sound" / "licenses"
        lic.mkdir(parents=True, exist_ok=True)
        (lic / f"{dest.stem}.txt").write_text(
            f"Source page: {page or 'not given'}\nLicense: {license_name or 'not given'}\nProvider: {via}\n"
            f"Fetched: {rec['created_at']}\n", encoding="utf-8")
    dest.with_suffix(".json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"imported {kind} {ident} -> {dest}")
    return dest
