"""Pin a voice take: the record of which take a final cut uses.

One file per beat, ``episode/approvals/voice--<beat>.json``. It records the take
file and its sha256, the inputs it was made from (prompt, provider, served model,
voice), who approved it, how and when. A final build reads only these, so a
re-recorded or swapped take can never slip into a final unnoticed.

This only writes down a decision already made: a person approves the draft, and
the takes that draft used get pinned. Drafts need no pins and are never stamped.

    animative pin <slug> --by "<name>" --via "approved the draft in chat"   # pin the draft's takes
    animative pin <slug> <beat> <take.wav> --by "<name>" --via "..."          # pin one take
    animative pin <slug> --check
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from animative import layout


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_hash(rec: dict) -> str:
    """The question asked, not the answer received: same inputs, same key."""
    key = json.dumps({k: rec.get(k) for k in ("prompt", "provider", "model_served", "voice")}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()


def beats(ep: layout.Episode) -> list[str]:
    out = []
    for n in ep.load("episode.json")["narration"]:
        front = (ep.dir / n["beat"]).read_text(encoding="utf-8").split("---")[1]
        out.append(dict(line.split(": ", 1) for line in front.strip().splitlines())["beat"])
    return out


def pin_voice(ep: layout.Episode, beat: str, take: str, by: str, via: str) -> None:
    wav = ep.takes / take
    rec = json.loads(wav.with_suffix(".json").read_text(encoding="utf-8"))
    if rec["beat"] != beat:
        raise SystemExit(f"{take} is a take of {rec['beat']}, not {beat}")
    out = ep.dir / "approvals" / f"voice--{beat}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "kind": "voice", "beat": beat, "state": "approved", "take": take, "sha256": sha256(wav),
        "input_hash": input_hash(rec), "provider": rec.get("provider"), "model_served": rec.get("model_served"),
        "voice": rec.get("voice"), "approved_by": by, "via": via,
        "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }, indent=1) + "\n", encoding="utf-8")
    print(f"pinned {beat}: {take}")


def pin_draft(ep: layout.Episode, by: str, via: str) -> None:
    """Pin exactly the takes the last draft was timed from."""
    timing = layout.Episode(ep.slug).out / "timing.json"
    if not timing.exists():
        raise SystemExit("no draft timing yet: build a draft first (animative draft <slug>)")
    used = json.loads(timing.read_text(encoding="utf-8"))["beats"]
    missing = [b["id"] for b in used if not b["take"]]
    if missing:
        raise SystemExit("the draft has no voice for: " + ", ".join(missing))
    for b in used:
        pin_voice(ep, b["id"], b["take"], by, via)


def check(ep: layout.Episode) -> dict[str, str]:
    """Return beat -> pinned take. Refuse, naming every beat, if any is missing or stale."""
    pinned, bad = {}, []
    for beat in beats(ep):
        p = ep.dir / "approvals" / f"voice--{beat}.json"
        if not p.exists():
            bad.append(f"{beat}: no approval")
            continue
        a = json.loads(p.read_text(encoding="utf-8"))
        wav = ep.takes / a["take"]
        if not wav.exists():
            bad.append(f"{beat}: pinned take {a['take']} is not in assets/voice/takes")
        elif sha256(wav) != a["sha256"]:
            bad.append(f"{beat}: {a['take']} differs from the pinned bytes")
        elif input_hash(json.loads(wav.with_suffix(".json").read_text(encoding="utf-8"))) != a["input_hash"]:
            bad.append(f"{beat}: inputs changed since approval (stale)")
        else:
            pinned[beat] = a["take"]
    if bad:
        raise SystemExit("a final reads only pinned takes, and these are not pinned:\n  " + "\n  ".join(bad))
    return pinned
