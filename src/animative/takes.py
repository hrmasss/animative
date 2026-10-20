"""Score every voice take against the script, so a person can pick by ear faster.

For each take: length, how many script words the transcript heard, the words it
missed or added, and how loud the shouted lines are against the rest. A word in
"added" that is not a spelling variant usually means a stage note was spoken
aloud: re-record that beat. This picks nothing and pins nothing; it writes
``assets/voice/takes/report.json`` and prints a table.

    animative takes <slug>
"""
from __future__ import annotations

import difflib
import json
import subprocess
from pathlib import Path

from animative import build as A


def rms_db(wav: Path, t0: float, t1: float) -> float:
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(wav),
                          "-f", "f32le", "-ac", "1", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype="<f4")
    return float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)) if len(x) else -99.0


def report(slug: str) -> list[dict]:
    ep = A.Ep(slug)
    beats = A.read_beats(ep)
    d = ep.scratch / "voice" / "takes"
    rows = []
    for b in beats:
        for wav in sorted(d.glob(f"{b['id']}--*.wav")):
            heard = A.whisper_words(ep, wav)
            script = A.script_words(b)
            a = [A.norm(w["w"]) for w in script]
            h = [A.norm(w["w"]) for w in heard]
            sm = difflib.SequenceMatcher(a=a, b=h, autojunk=False)
            matched = sum(blk.size for blk in sm.get_matching_blocks())
            missed, added = [], []
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op in ("delete", "replace"):
                    missed += [script[i]["w"] for i in range(i1, i2)]
                if op in ("insert", "replace"):
                    added += [heard[j]["w"] for j in range(j1, j2)]
            aligned = A.align(A.script_words(b), heard, 0.0, A.wav_seconds(wav))
            shout = [w for w in aligned if w["shout"]]
            calm = [w for w in aligned if not w["shout"]]
            lift = None
            if shout and calm:
                s = sum(rms_db(wav, w["t0"], w["t1"]) for w in shout) / len(shout)
                c = sum(rms_db(wav, w["t0"], w["t1"]) for w in calm) / len(calm)
                lift = round(s - c, 1)
            rows.append({"take": wav.name, "beat": b["id"], "seconds": round(A.wav_seconds(wav), 2),
                         "match": round(matched / max(1, len(a)), 3), "missed": missed, "added": added, "shout_lift_db": lift})
    (d / "report.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for r in rows:
        print(f"{r['take']:34s} {r['seconds']:6.1f}s match {r['match']:.2f} shout+{r['shout_lift_db']} "
              f"missed {' '.join(r['missed'])[:60]!r} added {' '.join(r['added'])[:60]!r}")
    return rows
