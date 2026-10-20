#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26", "pillow>=10"]
# ///
"""Build an animative episode: per-shot HyperFrames renders, a sound mix, one file.

Inputs are authored and live in ``projects/<slug>/episode/``: ``episode.json``
(shots), ``beats/*.md`` (every spoken word), ``edit.json`` (which file and
in-point each shot uses, anchors for impacts and effects, inserted b-roll).
Gathered media lives in ``projects/<slug>/assets/``. Everything this builds is
derived and lands in ``projects/<slug>/build/<draft|final>/``; the cut lands in
``projects/<slug>/videos/``.

Timing follows the voice when takes exist under ``assets/voice/takes/``, and the
planned whole seconds otherwise. Shot boundaries land on whole frames at the
episode's rational rate; nothing here holds a decimal frame rate. A draft uses
the newest (or named) take per beat; a final reads only pinned takes.

No frame is ever stamped. A draft looks exactly like a final, smaller.

    animative draft <slug>          # timing, compose, render, mix, assemble
    animative final <slug>          # the same at 1080p, from pinned takes
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from contextlib import contextmanager
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

import numpy as np

from animative import config, layout

TAG = re.compile(r"\[([^\]]+)\]")
SR = 48000
W, H = 960, 540
def lock_file() -> Path:
    return config.user_cache_dir() / "render.lock"

#: Natural Earth 110m countries, public domain. Fetched once for the map graphics.
WORLD_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
             "geojson/ne_110m_admin_0_countries.geojson")
SHOUT_TAGS = {"shout", "scream"}
PAUSE = 0.5          # a [beat] tag, in seconds
LINE_GAP = 0.22      # planned gap between lines when there is no voice yet


# ---------------------------------------------------------------- paths
class Ep(layout.Episode):
    """An episode being built, as a draft or as the final."""

    def __init__(self, slug: str, final: bool = False):
        super().__init__(slug, final=final)
        if not self.exists():
            raise SystemExit(f"no episode at {self.episode_json} (animative new {slug})")
        self.id = self.slug
        self.scratch = self.assets
        self.episode = self.load("episode.json")
        self.edit = self.load("edit.json")
        fr = self.episode["frame_rate"]
        self.fps = Fraction(fr["num"], fr["den"])
        self.pins: dict[str, str] = {}
        if final:
            from animative import pin
            self.pins = pin.check(self)

    def frames(self, t: float) -> int:
        return round(Fraction(t).limit_denominator(100000) * self.fps)

    def secs(self, f: int) -> float:
        return float(Fraction(f) / self.fps)


def npx() -> str:
    """npx itself: on Windows it is npx.cmd, which subprocess cannot find by bare name."""
    found = shutil.which("npx")
    if not found:
        raise SystemExit("npx not found: install Node 22+ (HyperFrames renders through it)")
    return found


def hyperframes(*args: str) -> list[str]:
    return [npx(), "--prefix", str(layout.kit_dir()), "hyperframes", *args]


@contextmanager
def render_lock():
    """One render at a time on this machine; renders saturate every core they get."""
    lock = lock_file()
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+") as fh:
        if sys.platform == "win32":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


# ---------------------------------------------------------------- script
def read_beats(ep: Ep) -> list[dict]:
    beats = []
    for n in ep.episode["narration"]:
        p = ep.dir / n["beat"]
        _, front, body = p.read_text(encoding="utf-8").split("---", 2)
        meta = dict(line.split(": ", 1) for line in front.strip().splitlines())
        lines = []
        for raw in body.strip().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            parts = TAG.split(raw)
            # parts alternate text, tag, text, tag ...
            tags: list[str] = []
            items: list[dict] = []
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    tt = [t.strip() for t in part.split(",")]
                    if tt == ["beat"]:
                        items.append({"pause": PAUSE})
                    elif not items:
                        tags = tt
                    else:
                        items.append({"tags": tt})
                else:
                    for w in part.split():
                        items.append({"w": w})
            lines.append({"tags": tags, "items": items, "text": TAG.sub("", raw).strip()})
        beats.append({"id": meta["beat"], "file": n["beat"], "start": int(meta["start"]),
                      "end": int(meta["end"]), "lines": lines})
    return beats


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower().replace("ı", "i"))


def is_shout(word: str, tags: list[str]) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", word)
    caps = len(letters) >= 3 and letters.isupper() and letters not in {"FPV", "AVIC", "MQ", "XQ"}
    return caps or bool(SHOUT_TAGS & set(tags))


def script_words(beat: dict) -> list[dict]:
    """Every spoken word of a beat in order, with its line, tags and any pause before it."""
    out = []
    for li, line in enumerate(beat["lines"]):
        tags = list(line["tags"])
        pause = 0.0
        for it in line["items"]:
            if "pause" in it:
                pause += it["pause"]
            elif "tags" in it:
                tags = it["tags"]
            else:
                out.append({"w": it["w"], "line": li, "tags": tags, "pause_before": pause,
                            "shout": is_shout(it["w"], tags)})
                pause = 0.0
    return out


# ---------------------------------------------------------------- timing
def planned_words(beat: dict, t0: float, t1: float) -> list[dict]:
    ws = script_words(beat)
    gaps = sum(w["pause_before"] for w in ws) + LINE_GAP * (len(beat["lines"]) - 1)
    weight = [len(norm(w["w"])) + 2 for w in ws]
    speak = max(0.5, (t1 - t0) - gaps - 0.3)
    k = speak / sum(weight)
    t = t0 + 0.15
    last_line = 0
    for w, wt in zip(ws, weight, strict=True):
        if w["line"] != last_line:
            t += LINE_GAP
            last_line = w["line"]
        t += w["pause_before"]
        w["t0"], w["t1"] = t, t + wt * k * 0.92
        t += wt * k
    return ws


def take_for(ep: Ep, beat_id: str) -> Path | None:
    """The take a build uses for a beat.

    A final reads only pins (approvals/voice--<beat>.json), and pin.check refuses the whole
    build, naming every beat, if any is missing or stale. A draft uses the take edit.json
    names, else the newest.
    """
    if ep.final:
        return ep.scratch / "voice" / "takes" / ep.pins[beat_id]
    chosen = ep.edit.get("voice", {}).get(beat_id) if beat_id != "_" else None
    d = ep.scratch / "voice" / "takes"
    if chosen:
        return d / chosen
    cands = sorted(d.glob(f"{beat_id}--*.wav")) if d.is_dir() else []
    return cands[-1] if cands else None


def wav_seconds(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def whisper_words(ep: Ep, wav: Path) -> list[dict]:
    """Word timestamps for one take, cached beside it."""
    cache = wav.with_suffix(".words.json")
    if cache.exists():
        return json.loads(cache.read_text())
    tmp = ep.out / "transcribe"
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1")
    lang = ep.episode.get("language", "en")
    model = "small.en" if lang == "en" else "small"
    res = subprocess.run(hyperframes("transcribe", str(wav), "--dir", str(tmp), "--model", model,
                                     "--language", lang, "--json"),
                         capture_output=True, text=True, env=env, check=True)
    data = json.loads(res.stdout)
    words = json.loads(Path(data["transcriptPath"]).read_text())
    out = [{"w": w["text"].strip(), "t0": float(w["start"]), "t1": float(w["end"])} for w in words]
    cache.write_text(json.dumps(out, indent=1))
    return out


def align(script: list[dict], heard: list[dict], offset: float, length: float) -> list[dict]:
    """Put heard timestamps on the script's words. Unheard words are interpolated."""
    a = [norm(w["w"]) for w in script]
    b = [norm(w["w"]) for w in heard]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            s, h = script[blk.a + k], heard[blk.b + k]
            s["t0"], s["t1"] = h["t0"] + offset, h["t1"] + offset
    # interpolate the rest between known neighbours
    n = len(script)
    known = [i for i in range(n) if "t0" in script[i]]
    for i in range(n):
        if "t0" in script[i]:
            continue
        lo = max([k for k in known if k < i], default=None)
        hi = min([k for k in known if k > i], default=None)
        t_lo = script[lo]["t1"] if lo is not None else offset + 0.05
        t_hi = script[hi]["t0"] if hi is not None else offset + length - 0.05
        span = (hi if hi is not None else n) - (lo if lo is not None else -1)
        pos = i - (lo if lo is not None else -1)
        step = (t_hi - t_lo) / span
        script[i]["t0"] = t_lo + step * (pos - 1) + 0.01
        script[i]["t1"] = t_lo + step * pos - 0.01
    return script


def cmd_timing(ep: Ep) -> dict:
    beats = read_beats(ep)
    gap = ep.edit.get("beat_gap", 0.25)
    t = 0.0
    tb, words, voiced = [], [], []
    for b in beats:
        take = take_for(ep, b["id"])
        if take and take.exists():
            length = wav_seconds(take)
            ws = align(script_words(b), whisper_words(ep, take), t, length)
            tb.append({"id": b["id"], "t0": t, "t1": t + length, "take": take.name})
            voiced.append(b["id"])
            t += length + gap
        else:
            length = b["end"] - b["start"]
            ws = planned_words(b, t, t + length)
            tb.append({"id": b["id"], "t0": t, "t1": t + length, "take": None})
            t += length
        for w in ws:
            w["beat"] = b["id"]
        words += ws
    total = t + ep.edit.get("tail", 1.5)

    # shots: scale each beat's planned shots onto its actual span, then snap cuts to word gaps
    shots = []
    for b in beats:
        span = next(x for x in tb if x["id"] == b["id"])
        bshots = [s for s in ep.episode["shots"] if s["beat"] == b["id"]]
        k = (span["t1"] - span["t0"]) / (b["end"] - b["start"])
        bw = [w for w in words if w["beat"] == b["id"]]
        prev = span["t0"]
        for i, s in enumerate(bshots):
            t0 = span["t0"] + (s["start"] - b["start"]) * k
            cue = ep.edit.get("shots", {}).get(s["id"], {}).get("cue")
            if i > 0 and cue:
                # cut a little before the cue word: its first occurrence after the previous cut
                target = norm(cue[2:])
                hit = next((w for w in bw if w["t0"] > prev + 0.2 and norm(w["w"]) == target), None)
                if hit is None:
                    raise SystemExit(f"{s['id']}: cue {cue!r} not found in beat {b['id']}")
                t0 = hit["t0"] - 0.12
                shots.append({"id": s["id"], "beat": b["id"], "t0": t0})
                prev = t0
                continue
            if i > 0:
                cands = [(w1["t1"] + w2["t0"]) / 2 for w1, w2 in pairwise(bw) if w2["t0"] - w1["t1"] > 0.06]
                near = [c for c in cands if abs(c - t0) < 0.6]
                if near:
                    t0 = min(near, key=lambda c: abs(c - t0))
            shots.append({"id": s["id"], "beat": b["id"], "t0": t0})
            prev = t0
    # the first shot of every beat after the first starts where the previous beat's last word ends
    for i, s in enumerate(shots):
        nxt = shots[i + 1]["t0"] if i + 1 < len(shots) else total
        s["t1"] = nxt
    # whole frames, contiguous
    for s in shots:
        s["f0"], s["f1"] = ep.frames(s["t0"]), ep.frames(s["t1"])
    for a, b2 in pairwise(shots):
        b2["f0"] = a["f1"]
    shots[0]["f0"] = 0
    timing = {"fps": [ep.fps.numerator, ep.fps.denominator], "beats": tb, "words": words, "shots": shots,
              "total_frames": shots[-1]["f1"], "voiced": voiced,
              "source": "voice" if len(voiced) == len(beats) else ("partial" if voiced else "planned")}
    ep.out.mkdir(parents=True, exist_ok=True)
    (ep.out / "timing.json").write_text(json.dumps(timing, indent=1))
    print(f"timing: {timing['source']}, {len(shots)} shots, {ep.secs(timing['total_frames']):.2f} s")
    return timing


# ---------------------------------------------------------------- presenter
VIS_LETTERS = [("th", "L"), ("oo", "U"), ("ou", "O"), ("ow", "O"), ("ee", "E"), ("ea", "E"), ("ai", "AI"), ("ay", "AI")]
VIS_ONE = {**dict.fromkeys("mbp", "MBP"), **dict.fromkeys("fv", "FV"), "l": "L", "o": "O",
           **dict.fromkeys("uwq", "U"), "e": "E", **dict.fromkeys("aiy", "AI")}


def visemes(word: str) -> list[str]:
    w = norm(word)
    if w.isdigit():
        w = "number"
    out, i = [], 0
    while i < len(w):
        two = w[i:i + 2]
        hit = next((v for k, v in VIS_LETTERS if k == two), None)
        if hit:
            out.append(hit)
            i += 2
            continue
        c = w[i]
        if c == "e" and i == len(w) - 1 and len(w) > 2:
            i += 1
            continue
        out.append(VIS_ONE.get(c, "etc"))
        i += 1
    dedup = [v for j, v in enumerate(out) if j == 0 or v != out[j - 1]]
    return dedup or ["etc"]


def presenter_spec(ep: Ep, shot: dict, f0: int, f1: int, words: list[dict], ed: dict, prefix: str) -> dict | None:
    pr = shot.get("presenter")
    if not pr:
        return None
    char = ep.character
    rigj = json.loads((layout.character_dir(char) / "rig.json").read_text(encoding="utf-8"))
    lock = json.loads((layout.ensure_cut(char) / "rig.lock.json").read_text(encoding="utf-8"))["parts"]
    F = rigj["face"]
    expr = rigj["expressions"].get(pr.get("feeling", "neutral"), rigj["expressions"]["neutral"])
    # An example written for one host plays with any other: a pose this host does not have
    # becomes the pose for the shot's feeling, then the neutral pose.
    pose_name = pr["pose"]
    if pose_name not in lock or not lock[pose_name].get("face"):
        fallback = expr.get("pose") or rigj["expressions"]["neutral"]["pose"]
        print(f"  {shot['id']}: {char} has no pose {pose_name!r}, using {fallback!r}")
        pose_name = fallback
    pose = lock[pose_name]
    place = pr.get("placement", "")
    full = "full frame" in place
    target_h = 470 if full else 300
    s = target_h / pose["size"][1]
    pw, ph = pose["size"][0] * s, target_h
    if full:
        cx = 480 if shot.get("graphic", {}).get("component") != "end-card" else 240
    elif "left" in place:
        cx = 175
    elif "right" in place:
        cx = 790
    else:
        cx = 480
    cx += ed.get("presenter_dx", 0)
    x, y = cx - pw / 2, 548 - ph
    fx0, fy0, fx1, fy1 = pose["face"]["box"]
    by = pose["face"]["beard_y"]
    fw = (fx1 - fx0) * s
    fcx = (fx0 + fx1) / 2 * s
    ey = (fy0 + F["eye_y"] * (fy1 - fy0)) * s - expr.get("lift", 0) * fw
    by *= s
    base = "assets/character/"

    def part(name, pcx, pcy, scale, flip=False, rot=0):
        sz = lock[name]["size"]
        w, h = sz[0] * scale, sz[1] * scale
        return {"src": base + lock[name]["file"], "x": round(pcx - w / 2, 2), "y": round(pcy - h / 2, 2),
                "w": round(w, 2), "h": round(h, 2), "flip": flip, "rot": rot}

    es = F["eye_width"] * fw / lock[F["eye_ref"]]["size"][0]
    tilt = expr.get("tilt", 0)
    left, r = expr["eyes"]
    eyes = [part(left, fcx - F["eye_dx"] * fw, ey, es, rot=-tilt),
            part(left if r == "mirror" else r, fcx + F["eye_dx"] * fw, ey, es, flip=(r == "mirror"), rot=tilt)]
    blink = F.get("blink", "closed")
    closed = [part(blink, fcx - F["eye_dx"] * fw, ey, es), part(blink, fcx + F["eye_dx"] * fw, ey, es, flip=True)]
    nose = part(expr.get("nose", F["nose"]), fcx, ey + F["nose_y"] * (by - ey), F["nose_width"] * fw / lock[F["nose"]]["size"][0])
    ms = F["mouth_width"] * fw / lock[F["mouth_ref"]]["size"][0]
    my = by + F["mouth_y"] * fw
    vmap = {k: v["mouth"] for k, v in rigj["visemes"].items() if k != "_"}
    rest = expr["mouth"]
    shout = F.get("shout_mouth") or vmap.get("AI") or rest
    names = set(vmap.values()) | {rest, shout}
    mouths = {n: part(n, fcx, my, ms) for n in sorted(names)}  # sorted: a set's order changes run to run

    # lip-sync: the shot's words, in shot-local seconds
    t_shot0 = ep.secs(f0)
    dur = ep.secs(f1 - f0)
    frame = 1 / float(ep.fps)
    track = [[0.0, rest]]
    hits = []
    in_shot = [w for w in words if w["t1"] > t_shot0 and w["t0"] < t_shot0 + dur]
    for i, w in enumerate(in_shot):
        a, b = w["t0"] - t_shot0, w["t1"] - t_shot0
        vs = visemes(w["w"])
        slots = max(1, int((b - a) / (2 * frame)))
        if len(vs) > slots:
            idx = np.linspace(0, len(vs) - 1, slots).round().astype(int)
            vs = [vs[j] for j in idx]
        step = (b - a) / len(vs)
        for j, v in enumerate(vs):
            m = vmap.get(v, vmap["etc"])
            if w["shout"] and v in ("AI", "O", "E", "open"):
                m = shout
            track.append([round(max(0.0, a + j * step), 4), m])
        nxt = in_shot[i + 1]["t0"] - t_shot0 if i + 1 < len(in_shot) else None
        if nxt is None or nxt - b > 0.12:
            track.append([round(max(0.0, b), 4), rest])
        if w["shout"]:
            hits.append(round(a, 4))
    track = [t for t in track if t[0] < dur]
    track.sort(key=lambda t: t[0])

    h = int(hashlib.sha256(shot["id"].encode()).hexdigest()[:8], 16)
    blinks, t = [], 0.9 + (h % 100) / 100
    while t < dur - 0.2:
        blinks.append(round(t, 3))
        t += 2.4 + ((h >> (int(t * 7) % 24)) % 180) / 100
    entrance = ed.get("presenter_entrance") or ("left" if "from left" in place else "right" if "slides in right" in place else "pop")
    t_in = ed.get("presenter_in", 0.0)
    return {"pose": base + pose["file"], "x": round(x, 2), "y": round(y, 2), "w": round(pw, 2), "h": round(ph, 2),
            "eyes": eyes, "eyes_closed": closed, "nose": nose, "mouths": mouths, "mouth_track": track,
            "blinks": blinks, "hits": hits, "entrance": entrance, "t0": t_in, "bounce": "bounce" in place}


# ---------------------------------------------------------------- compose
def anchor(spec_at, words: list[dict], t_shot0: float, dur: float) -> float | None:
    """'w:BOOM' = when that word starts; 'w:BOOM+0.1' shifts; '0.4' = shot seconds; '-0.3' from the end."""
    if isinstance(spec_at, (int, float)):
        return spec_at if spec_at >= 0 else dur + spec_at
    m = re.match(r"w:([^+\-]+)([+\-][0-9.]+)?$", spec_at)
    if m:
        target = norm(m.group(1))
        off = float(m.group(2) or 0)
        for w in words:
            if norm(w["w"]) == target and w["t0"] >= t_shot0 - 0.3 and w["t0"] < t_shot0 + dur:
                return max(0.0, w["t0"] - t_shot0 + off)
        return None
    return float(spec_at)


def captions_for(words: list[dict], t_shot0: float, dur: float) -> list[dict]:
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        end_punct = bool(re.search(r"[.,!?…]$", w["w"]))
        nxt = words[i + 1] if i + 1 < len(words) else None
        brk = (len(cur) >= 4 or end_punct or nxt is None or nxt["line"] != w["line"] or nxt["beat"] != w["beat"]
               or (nxt and nxt["t0"] - w["t1"] > 0.35))
        if brk:
            groups.append(cur)
            cur = []
    out = []
    for gi, g in enumerate(groups):
        g0 = g[0]["t0"] - 0.04
        nxt0 = groups[gi + 1][0]["t0"] - 0.04 if gi + 1 < len(groups) else g[-1]["t1"] + 0.4
        g1 = min(g[-1]["t1"] + 0.35, nxt0)
        if g1 <= t_shot0 or g0 >= t_shot0 + dur:
            continue
        out.append({"t0": round(g0 - t_shot0, 4), "t1": round(g1 - t_shot0, 4),
                    "words": [{"w": w["w"], "t0": round(w["t0"] - t_shot0, 4), "t1": round(w["t1"] - t_shot0, 4), "shout": w["shout"]} for w in g]})
    return out


def shot_year(shot: dict) -> int | None:
    g = shot.get("graphic", {}).get("data", {})
    for d in (g, g.get("card", {})):
        y = d.get("year")
        if y:
            return int(str(y)[:4])
    return None


def copy_assets(ep: Ep) -> None:
    a = ep.hf / "assets"
    a.mkdir(parents=True, exist_ok=True)
    gsap = layout.kit_dir() / "node_modules" / "gsap" / "dist" / "gsap.min.js"
    if not gsap.exists():
        raise SystemExit("the render kit is not installed: run  animative setup")
    kit = config.KIT_SRC
    shutil.copytree(kit / "fonts", a.parent / "fonts", dirs_exist_ok=True)
    shutil.copy2(kit / "kit.js", ep.hf / "kit.js")
    shutil.copy2(kit / "kit.css", ep.hf / "kit.css")
    shutil.copy2(gsap, ep.hf / "gsap.min.js")
    if any(s.get("presenter") for s in ep.episode["shots"]):
        # a video with no host on screen needs no host at all
        shutil.copytree(layout.ensure_cut(ep.character), a / "character", dirs_exist_ok=True)
    world_js(ep, ep.hf / "world.js")
    grain(ep.hf / "assets" / "grain.png")


def world_js(ep: Ep, dest: Path) -> None:
    if dest.exists():
        return
    src = ep.scratch / "data" / "ne_110m_countries.geojson"
    if not src.exists():
        cached = config.user_cache_dir() / "data" / "ne_110m_countries.geojson"
        if not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            print("fetching Natural Earth countries (public domain) for the map graphics")
            urllib.request.urlretrieve(WORLD_URL, cached)
        src = cached
    gj = json.loads(src.read_text(encoding="utf-8"))
    out = {}
    for f in gj["features"]:
        code = f["properties"].get("ADM0_A3") or f["properties"]["NAME"]
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        d = []
        for poly in polys:
            for ring in poly:
                pts = [f"{(lon + 180) / 360 * 2000:.1f},{(90 - lat) / 180 * 1000:.1f}" for lon, lat in ring]
                d.append("M" + "L".join(pts) + "Z")
        out[code] = "".join(d)
    dest.write_text("window.WORLD=" + json.dumps(out, separators=(",", ":")) + ";", encoding="utf-8")


def grain(dest: Path) -> None:
    if dest.exists():
        return
    from PIL import Image
    rs = np.random.default_rng(7)
    n = (rs.random((256, 256)) * 255).astype("uint8")
    Image.fromarray(n, "L").save(dest)


def media_asset(ep: Ep, rel: str, start: float = 0, precrop: list | None = None) -> str:
    """Link a scratch file into the HyperFrames project; return its project path.

    ``precrop`` is [x0, y0, x1, y1] as fractions: cut a photo down before it is framed,
    for example to keep bystanders' faces out of every crop of it.
    """
    src = (ep.scratch / rel).resolve()
    if not src.exists():
        raise SystemExit(f"missing media: {src}")
    # A draft never needs more than 1280 px of video; a 1080p final needs 1920, or it upscales.
    video = src.suffix.lower() in (".mp4", ".mov", ".webm", ".m4v")
    vw = 1920 if ep.final else 1280
    tag = ("-c" + "-".join(f"{c:g}" for c in precrop)) if precrop else ""
    # Videos are cut to the 20 s from the in-point, so the page's media start is 0 plus any offset.
    dst = ep.hf / "assets" / "media" / (Path(rel).stem + (f"-at{start:g}-w{vw}.mp4" if video else f"{tag}.jpg"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        if video:
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", "20", "-i", str(src), "-an",
                 "-vf", f"scale='min({vw},iw)':-2",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "18" if ep.final else "20", "-pix_fmt", "yuv420p", str(dst)])
        else:
            vf = "scale='min(1920,iw)':-2"
            if precrop:
                x0, y0, x1, y1 = precrop
                vf = f"crop=iw*{x1 - x0:g}:ih*{y1 - y0:g}:iw*{x0:g}:ih*{y0:g}," + vf
            run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-q:v", "3", str(dst)])
    return "assets/media/" + dst.name


def thumb(ep: Ep, rel: str, at: float = 1.0) -> str:
    src = ep.scratch / rel
    dst = ep.hf / "assets" / "thumbs" / (Path(rel).stem + ".jpg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        if src.suffix.lower() in (".mp4", ".mov", ".webm", ".m4v"):
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(src), "-frames:v", "1", "-vf", "scale=320:-2", str(dst)])
        else:
            run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "scale=320:-2", str(dst)])
    return "assets/thumbs/" + dst.name


def cmd_compose(ep: Ep) -> None:
    timing = json.loads((ep.out / "timing.json").read_text(encoding="utf-8"))
    copy_assets(ep)
    words = timing["words"]
    edits = ep.edit.get("shots", {})
    srcs = ep.edit.get("sources", {})
    shots = {s["id"]: s for s in ep.episode["shots"]}
    prev_year = None
    kit_bytes = b"".join((ep.hf / n).read_bytes() for n in ("kit.js", "kit.css", "world.js"))
    index = []
    for st in timing["shots"]:
        sid = st["id"]
        shot = shots[sid]
        ed = edits.get(sid, {})
        f0, f1 = st["f0"], st["f1"]
        dur = ep.secs(f1 - f0)
        t0 = ep.secs(f0)
        bg = []
        for seg in ed.get("bg", [{"source": sid}] if sid in srcs else []):
            if "source" in seg and seg["source"] not in srcs:
                print(f"  {sid}: no file for source {seg['source']} yet, skipped")
                continue
            src = srcs[seg["source"]] if "source" in seg else seg
            if not (ep.scratch / src["file"]).exists() and not ep.final:
                # a draft is built while sourcing is still going on: leave the gap, say so
                print(f"  {sid}: {src['file']} not fetched yet, skipped")
                continue
            seg_t0 = anchor(seg.get("at", 0), words, t0, dur) or 0.0
            seg_t1 = anchor(seg["until"], words, t0, dur) if "until" in seg else None
            kind = "video" if Path(src["file"]).suffix.lower() in (".mp4", ".mov", ".webm", ".m4v") else "image"
            bg.append({"kind": kind, "src": media_asset(ep, src["file"], src.get("in", 0), src.get("precrop")), "media_start": seg.get("in_offset", 0),
                       "fit": src.get("fit", "cover"), "move": seg.get("move", shot.get("movement")), "grade": seg.get("grade", ed.get("grade")),
                       "dutch": shot.get("angle") == "dutch", "t0": seg_t0, "t1": seg_t1, "crops": src.get("crops"),
                       "crop": seg.get("crop"), 
                       "len": min(20, src.get("len", 20))})
        for i in range(len(bg) - 1):
            if bg[i]["t1"] is None:
                bg[i]["t1"] = bg[i + 1]["t0"]
        bg = split_long(bg, dur)
        graphics = []
        g = shot.get("graphic")
        if g:
            gd = dict(g)
            gd["data"] = {**g.get("data", {}), **ed.get("graphic_data", {})}
            gd["t0"] = anchor(ed.get("graphic_at", 0.15 if bg else 0), words, t0, dur)
            if "graphic_until" in ed:
                gd["t1"] = anchor(ed["graphic_until"], words, t0, dur)
            graphics.append(gd)
        for extra in ed.get("graphics", []):
            e = dict(extra)
            e["t0"] = anchor(e.get("at", 0), words, t0, dur)
            if "until" in e:
                e["t1"] = anchor(e["until"], words, t0, dur)
            graphics.append(e)
        impacts = [x for x in (anchor(a, words, t0, dur) for a in ed.get("impacts", [])) if x is not None]
        pres = presenter_spec(ep, shot, f0, f1, words, ed, sid)
        if pres and "presenter_in" in ed:
            pres["t0"] = anchor(ed["presenter_in"], words, t0, dur) or 0.0
        place = (shot.get("presenter") or {}).get("placement", "")
        year = ed.get("year", shot_year(shot))
        ticker = None
        if ed.get("ticker", True) and (year or prev_year) and sid not in ep.edit.get("no_ticker", []):
            y = year or prev_year
            ticker = {"from": prev_year or y, "to": y, "enter": prev_year is None}
            prev_year = y
        spec = {
            "id": sid, "dur": dur, "fps_num": ep.fps.numerator, "fps_den": ep.fps.denominator,
            "bg": bg, "backdrop": ed.get("backdrop", "grid"), "move": shot.get("movement"), "angle": shot.get("angle"),
            "grade": ed.get("grade"), "graphics": graphics, "presenter": pres, "impacts": impacts,
            "captions": captions_for(words, t0, dur) if ed.get("captions", True) else [], "ticker": ticker,
            "card_side": "right" if ("left" in place or ed.get("card_side") == "right") else "left",
            "grain": "assets/grain.png", "scan": ed.get("scan", False), "notes": ed.get("notes", False),
            "silhouette": ed.get("silhouette", False)
        }
        hl = g.get("data", {}).get("highlight") if g else None
        if hl:
            # a map lighting up a list of countries: edit.json -> highlights.<name>, highlight_home.<name>
            spec["highlight_names"] = ep.edit.get("highlights", {}).get(hl, [])
            spec["highlight_home"] = ep.edit.get("highlight_home", {}).get(hl)
        if g and g["component"] == "timeline":
            spec["timeline_items"] = timeline_items(ep, shots, srcs)
        html = page(spec)
        (ep.hf / f"{sid}.html").write_text(html, encoding="utf-8")
        # key on every input the render reads: the page, the kit, and the media it names
        h = hashlib.sha256(html.encode() + kit_bytes)
        for b in bg:
            h.update((ep.hf / b["src"]).read_bytes()[:65536])
        index.append({"id": sid, "f0": f0, "f1": f1, "hash": h.hexdigest()[:16]})
    # the CLI wants an index.html in the project even when it renders another file with -c
    shutil.copy2(ep.hf / f"{index[0]['id']}.html", ep.hf / "index.html")
    (ep.out / "shots.json").write_text(json.dumps(index, indent=1))
    print(f"composed {len(index)} shots -> {ep.hf}")


MOVES = ["dolly_in", "pan", "zoom_out", "truck", "zoom_in"]
# No picture holds longer than this. 4.2 s read as one still held for 8 to 12 s in review,
# because a new camera move on the same framing does not register as a cut. Each part now
# gets a different crop as well; a source can name its own crops (its details) in edit.json.
MAX_HOLD = 3.6
CROPS = [None, [1.7, 28, 45], [1.7, 74, 40], [1.45, 50, 78]]


def split_long(bg: list[dict], dur: float) -> list[dict]:
    """Cut 2 to 4 seconds a shot: a segment held longer becomes several framings of the same source."""
    out = []
    for s in bg:
        t0, t1 = s["t0"], s["t1"] if s["t1"] is not None else dur
        n = int(np.ceil((t1 - t0) / MAX_HOLD))
        if n <= 1:
            out.append(s)
            continue
        step = (t1 - t0) / n
        first = MOVES.index(s["move"]) if s.get("move") in MOVES else 0
        crops = s.get("crops") or CROPS
        for k in range(n):
            part = dict(s, t0=t0 + k * step, t1=t0 + (k + 1) * step if k < n - 1 else s["t1"],
                        move=s.get("move") if k == 0 else MOVES[(first + 2 * k) % len(MOVES)],
                        crop=crops[k % len(crops)])
            if s["kind"] == "video":
                # stay inside the clip's usable range: past it is often a different scene or a face
                usable = max(step, s.get("len", 20) - step)
                part["media_start"] = s.get("media_start", 0) + (k * step) % usable
            out.append(part)
    return out


def timeline_items(ep: Ep, shots: dict, srcs: dict) -> list[dict]:
    items = []
    for sid, s in shots.items():
        g = s.get("graphic", {})
        d = g.get("data", {})
        card = d if g.get("component") == "name-card" else d.get("card")
        if not card or not card.get("year"):
            continue
        it = {"year": int(card["year"]), "name": card["name"]}
        if sid in srcs:
            if (ep.scratch / srcs[sid]["file"]).exists():
                it["src"] = thumb(ep, srcs[sid]["file"], srcs[sid].get("in", 0) + 1)
        items.append(it)
    # entries the shot list has no name card for: edit.json -> timeline_extra
    for extra in ep.edit.get("timeline_extra", []):
        src = extra.get("source")
        have = src in srcs and (ep.scratch / srcs[src]["file"]).exists()
        items.append({"year": int(extra["year"]), "name": extra["name"],
                      "src": thumb(ep, srcs[src]["file"]) if have else None})
    items.sort(key=lambda i: i["year"])
    return items


def page(spec: dict) -> str:
    sid = spec["id"]
    blob = json.dumps(spec).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<title>{sid}</title>
<link rel="stylesheet" href="kit.css" />
<script src="gsap.min.js"></script>
<script src="world.js"></script>
</head>
<body>
<div id="root" data-composition-id="{sid}" data-start="0" data-width="{W}" data-height="{H}" data-duration="{spec['dur']:.6f}"></div>
<script id="shot-spec" type="application/json">{blob}</script>
<script src="kit.js"></script>
</body>
</html>
"""


# ---------------------------------------------------------------- render
def cmd_render(ep: Ep, only: list[str]) -> None:
    index = json.loads((ep.out / "shots.json").read_text())
    rdir = ep.out / "renders"
    rdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1")
    # Docker pins Chromium, fonts and encoder, so two machines render identical frames. It is
    # opt-in (edit.json render_docker, or ANIMATIVE_DOCKER=1): a local render is the default.
    docker = bool(ep.edit.get("render_docker", False)) or os.environ.get("ANIMATIVE_DOCKER") == "1"
    fps = f"{ep.fps.numerator}/{ep.fps.denominator}"
    # Shots render CONCURRENT at a time, each with its own Chrome workers, inside one flock'd
    # build: 6 vCPU take two 1080p shots (2 workers each) or three 540p shots without thrashing.
    jobs = int(os.environ.get("ANIMATIVE_CONCURRENT", "2" if ep.final else "3"))
    workers = os.environ.get("ANIMATIVE_WORKERS", "2")
    todo = []
    for s in index:
        if only and s["id"] not in only:
            continue
        out = rdir / f"{s['id']}.mp4"
        stamp = rdir / f"{s['id']}.hash"
        if out.exists() and stamp.exists() and stamp.read_text() == s["hash"] and not only:
            continue
        todo.append(s)

    def one(s: dict) -> str:
        out = rdir / f"{s['id']}.mp4"
        cmd = hyperframes("render", str(ep.hf), "-c", f"{s['id']}.html",
                          "-o", str(out), "--fps", fps, "--quiet", "--workers", workers)
        if ep.final:
            cmd += ["--resolution", "landscape", "--quality", "high"]
        if docker:
            cmd.append("--docker")
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            return f"{s['id']}: FAILED\n{res.stderr[-1500:]}"
        got, want = probe_frames(out), s["f1"] - s["f0"]
        (rdir / f"{s['id']}.hash").write_text(s["hash"])
        return f"{s['id']}: ok" + ("" if got == want else f"  warning: {got} frames, plan says {want}")

    from concurrent.futures import ThreadPoolExecutor
    with render_lock():
        failed = []
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for line in pool.map(one, todo):
                print("render", line, flush=True)
                if "FAILED" in line:
                    failed.append(line)
        if failed:
            raise SystemExit(f"{len(failed)} shot(s) failed to render")


def probe_frames(p: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout
    try:
        return int(out.strip())
    except ValueError:
        return -1


# ---------------------------------------------------------------- sound
def decode(p: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).copy()


def loudnorm(p: Path, lufs: float, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "2", str(dest)])
    return dest


def db(x: float) -> float:
    return 10 ** (x / 20)


def sfx_lookup(ep: Ep) -> tuple[dict, list[str]]:
    idx = json.loads((ep.scratch / "sound/index.json").read_text())
    by = {norm(e["name"]): e for e in idx}
    return by, list(by)


def cmd_mix(ep: Ep) -> Path:
    timing = json.loads((ep.out / "timing.json").read_text())
    total = ep.secs(timing["total_frames"])
    n = int(total * SR) + SR
    mixv = np.zeros((n, 2), dtype=np.float32)
    work = ep.out / "audio"
    # voice
    active = np.zeros(n, dtype=np.float32)
    for b in timing["beats"]:
        if not b["take"]:
            continue
        v = decode(loudnorm(ep.scratch / "voice/takes" / b["take"], -16, work / ("v-" + b["take"])))
        i = int(b["t0"] * SR)
        mixv[i:i + len(v)] += v[: n - i]
    voiced = set(timing.get("voiced", []))
    for w in timing["words"]:
        # duck only under real voice: a beat with no take yet has planned words, not sound
        if w["beat"] not in voiced:
            continue
        a, z = int((w["t0"] - 0.08) * SR), int((w["t1"] + 0.25) * SR)
        active[max(0, a):z] = 1.0
    # duck envelope: 12 dB under the voice, 80 ms attack, 300 ms release
    env = np.ones(n, dtype=np.float32)
    duck = db(-12)
    att, rel = 0.08 * SR, 0.30 * SR
    g = 1.0
    for i in range(0, n, 240):
        target = duck if active[i] else 1.0
        rate = 240 / (att if target < g else rel)
        g = g + (target - g) * min(1.0, rate * 3)
        env[i:i + 240] = g
    music = np.zeros((n, 2), dtype=np.float32)
    m = ep.edit.get("music")
    if m:
        mv = decode(loudnorm(ep.scratch / m["file"], m.get("lufs", -20), work / "music.wav"))
        off = int(m.get("in", 0) * SR)
        mv = mv[off:]
        reps = int(np.ceil(n / len(mv)))
        mv = np.concatenate([mv] * reps)[:n]
        fade_in, fade_out = int(0.4 * SR), int(2.5 * SR)
        mv[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
        end = int(total * SR)
        mv[end - fade_out:end] *= np.linspace(1, 0, fade_out)[:, None]
        mv[end:] = 0
        music = mv * env[:, None] * db(m.get("gain_db", 0))
    # effects
    by, keys = sfx_lookup(ep)
    edits = ep.edit.get("shots", {})
    shots = {s["id"]: s for s in ep.episode["shots"]}
    fx = np.zeros((n, 2), dtype=np.float32)
    cache: dict[str, np.ndarray] = {}
    placed = []
    sfx_map = {norm(k): v for k, v in ep.edit.get("sfx_map", {}).items()}

    def place(name: str, at: float, gain_db: float):
        key = sfx_map.get(norm(name), norm(name))
        if key == "SKIP":
            return
        key = norm(key)
        if key not in by:
            close = difflib.get_close_matches(key, keys, n=1, cutoff=0.5)
            if not close:
                placed.append((name, at, "MISSING"))
                return
            key = close[0]
        e = by[key]
        if key not in cache:
            cache[key] = decode(loudnorm(ep.scratch / "sound" / e["file"], -20, work / "sfx" / (key + ".wav")))
        s = cache[key]
        i = max(0, int(at * SR))
        k = min(len(s), n - i)
        fx[i:i + k] += s[:k] * db(gain_db)
        placed.append((name, round(at, 3), e["name"]))

    for st in timing["shots"]:
        sid = st["id"]
        t0 = ep.secs(st["f0"])
        dur = ep.secs(st["f1"] - st["f0"])
        ed = edits.get(sid, {})
        if "sfx" in ed:
            for e in ed["sfx"]:
                at = anchor(e.get("at", 0), timing["words"], t0, dur)
                if at is not None:
                    for r in range(e.get("repeat", 1)):
                        place(e["n"], t0 + at + r * e.get("every", 0.35), e.get("gain", 0))
        else:
            names = shots[sid].get("sfx", [])
            imps = [anchor(a, timing["words"], t0, dur) for a in ed.get("impacts", [])]
            for j, nm in enumerate(names):
                rep = 1
                mrep = re.search(r"\bx(\d)$", nm)
                if mrep:
                    rep, nm = int(mrep.group(1)), nm[: mrep.start()].strip()
                at = -0.05 if j == 0 else (imps[0] if imps and imps[0] is not None else dur * 0.45)
                for r in range(rep):
                    place(nm, t0 + max(0, at) + r * 0.35, 0)
        if ed.get("cut_whoosh", True) and st["f0"] > 0:
            place("whoosh", t0 - 0.12, -8)
    (ep.out / "sfx-placed.json").write_text(json.dumps(placed, indent=1))
    mix = mixv + music + fx * db(ep.edit.get("sfx_gain_db", -7.5))
    peak = float(np.abs(mix).max()) or 1.0
    if peak > db(-1):
        mix *= db(-1) / peak
    mix = mix[: int(total * SR)]
    dest = ep.out / "mix.wav"
    run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_s16le", str(dest)],
        input=mix.astype("<f4").tobytes())
    env_db = 20 * np.log10(env[: int(total * SR)] + 1e-9)
    print(f"music duck: {env_db.min():.1f} dB at deepest, {np.mean(env_db < -11.5) * 100:.0f}% of the cut ducked")
    missing = [p for p in placed if p[2] == "MISSING"]
    print(f"mix: {total:.2f} s, {len(placed) - len(missing)} effects placed, {len(missing)} missing -> {dest}")
    for p in missing:
        print("  missing sfx:", p[0])
    return dest


# ---------------------------------------------------------------- assemble
def cmd_assemble(ep: Ep) -> Path:
    index = json.loads((ep.out / "shots.json").read_text())
    rdir = ep.out / "renders"
    lst = ep.out / "concat.txt"
    lst.write_text("".join(f"file '{(rdir / (s['id'] + '.mp4')).as_posix()}'\n" for s in index), encoding="utf-8")
    video = ep.out / "picture.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])
    dest = ep.video()
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(ep.out / "mix.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18" if ep.final else "21", "-pix_fmt", "yuv420p",
         "-r", f"{ep.fps.numerator}/{ep.fps.denominator}", "-c:a", "aac", "-b:a", "192k", "-shortest",
         "-movflags", "+faststart", str(dest)])
    print(("final" if ep.final else "draft") + " ->", dest)
    return dest


def build_all(ep: Ep) -> Path:
    cmd_timing(ep)
    cmd_compose(ep)
    cmd_render(ep, [])
    cmd_mix(ep)
    return cmd_assemble(ep)
