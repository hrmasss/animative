"""Generate an episode's illustration stills with the agy CLI.

Reads ``episode/generated.json`` and writes each still, plus a provenance record
beside it, to ``assets/generated/agy/``. A still that already exists is never
generated again. agy runs in print mode only, in the foreground, with the output
directory as its working directory so it cannot touch the repo.

The image tool has its own quota per account, and an exhausted account answers
with a 429 that otherwise looks like a hang, so every call has a hard timeout.
With ``aswap`` installed (several agy accounts) a quota answer moves on to the
next account; with plain ``agy`` it stops and says so.

Other image providers (Codex, ChatGPT or Gemini in a browser, by hand) make the
file however they make it, then ``animative import <slug> still <id> <file>``.

    animative stills <slug> [id ...] [--accounts a3,a2]
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime

from animative import layout

TIMEOUT_S = 330


def ask(name: str, prompt_text: str) -> str:
    return (f"Use your image generation tool to create ONE image and save it in the current directory as "
            f"{name}. Prompt: '{prompt_text}' Do not create or edit any other file. Reply with the saved path only.")


def generate(slug: str, only: list[str], accounts: list[str] | None = None) -> None:
    ep = layout.Episode(slug)
    spec = ep.load("generated.json")
    if not spec.get("stills"):
        raise SystemExit(f"no stills listed in {ep.dir / 'generated.json'}")
    out = ep.assets / "generated" / "agy"
    out.mkdir(parents=True, exist_ok=True)
    aswap, agy = shutil.which("aswap"), shutil.which("agy")
    if not (aswap or agy):
        raise SystemExit("agy not found on PATH")
    slots: list[str | None] = list(accounts or ([] if not aswap else ["a1", "a2", "a3", "a4", "a5", "a6", "a7"])) or [None]
    dead: set[str | None] = set()
    for s in spec["stills"]:
        if only and s["id"] not in only:
            continue
        png = out / f"{s['id']}.png"
        if png.exists():
            continue
        full = f"{s['prompt']} {spec.get('rules', '')}".strip()
        for acct in slots:
            if acct in dead:
                continue
            if aswap and acct:
                cmd = [aswap, "exec", acct, "--", "-p", ask(png.name, full), "--print-timeout", f"{TIMEOUT_S - 30}s",
                       "--dangerously-skip-permissions"]
            else:
                cmd = [agy or "agy", "-p", ask(png.name, full), "--dangerously-skip-permissions"]
            try:
                res = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=TIMEOUT_S)
                said = (res.stdout + res.stderr).strip()
            except subprocess.TimeoutExpired:
                said = "timeout"
            if png.exists():
                model = re.search(r"gemini-[\w.\-]+image[\w.\-]*", said)
                rec = {"id": s["id"], "for": s.get("for"), "tool": "agy generate_image", "account": acct,
                       "model_reported": model.group(0) if model else None, "prompt": full,
                       "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                       "use": "illustration only, never evidence"}
                (out / f"{s['id']}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
                print(f"{s['id']}: ok" + (f" on {acct}" if acct else ""), flush=True)
                break
            if re.search(r"429|quota|exhaust|capacity", said, re.I) or said == "timeout":
                print(f"{s['id']}: {acct or 'agy'} out of image quota ({said[-120:]!r})", flush=True)
                dead.add(acct)
                continue
            print(f"{s['id']}: failed: {said[-200:]!r}", flush=True)
            break
        else:
            print(f"{s['id']}: no account left with image quota", flush=True)
