"""Record an episode's narration, one take per beat, with whichever voice was chosen.

Direction tags in ``beats/*.md`` become plain-language delivery notes, because
Gemini takes direction in words, not markup. The pronunciation glossary in
``episode.json`` is applied two ways: terms said letter by letter are respelled
in the text, the rest go in as notes. Every take lands in
``assets/voice/takes/<beat>--<voice>--NN.wav`` beside a JSON record of exactly
what was asked and which model the provider says answered.

Providers (chosen once, see providers.py):

* ``gemini-api``  Gemini TTS with GEMINI_API_KEY (several keys rotate on quota)
* ``vertex``      Gemini TTS on Vertex AI: gcloud Application Default
                  Credentials and a project (``vertex_project`` in the choice)
* ``edge``        edge_tts. Free, but reads flat: the tags become plain text
* ``kokoro``      local Kokoro (the kokoro extra). Free, also flat
* browser or manual voices arrive through ``animative import <slug> voice``

    animative voice <slug> prompt [beat ...]     # what would be sent, spend nothing
    animative voice <slug> estimate              # cost before any take
    animative voice <slug> record [beat ...]
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import wave
from datetime import UTC, datetime
from pathlib import Path

from animative import keys, layout, providers

TAG = re.compile(r"\[([^\]]+)\]")

# What each tag means, in the words a voice director would use. Mirrors the
# direction table in the skill's recipe.
DIRECTION = {
    "scream": "SCREAM it: raw, full volume, high and short",
    "shout": "SHOUT it: full volume, raw energy",
    "whisper": "whisper, close to the mic",
    "low": "low and quiet, close",
    "dark": "dark and ominous, lower pitch, slower",
    "fast": "fast",
    "quick": "quick",
    "breathless": "breathless, urgent",
    "rising": "building, rising energy toward the next line",
    "slow": "slow, with weight",
    "big": "big, announcer scale, epic",
    "heavy": "heavy and weighty",
    "awe": "with awe and wonder",
    "excited": "excited, high energy, no shouting",
    "storyteller": "warm, conversational storyteller",
}
DEFAULT_STYLE = (
    "You are the host of a lively YouTube explainer. Your delivery is energetic and dramatic, "
    "with real shouts and screams where marked."
)
READ_RULES = (
    " Read the script below exactly as written. Each line starts with a delivery note in "
    "parentheses: follow it, never speak it. An ellipsis means a short dramatic pause."
)
PACE = {
    "": "",
    "fast": " Keep a fast pace throughout, like a hype YouTube narrator: no dragging, short pauses, punchy.",
}

#: Published prices per million tokens on 2026-10-18 (Vertex and the Gemini API
#: list the same rates). Audio output is 25 tokens a second. Re-check before
#: trusting an estimate for a long series.
PRICES = {"flash": {"in": 0.50, "out": 10.00}, "pro": {"in": 1.00, "out": 20.00}}
AUDIO_TOKENS_PER_S = 25

DEFAULTS = {
    "gemini-api": {"model": "gemini-2.5-pro-preview-tts", "voice": "Fenrir"},
    "vertex": {"model": "gemini-2.5-pro-tts", "voice": "Fenrir"},
    "edge": {"model": "edge-tts", "voice": "en-US-GuyNeural"},
    "kokoro": {"model": "kokoro", "voice": "am_michael"},
}


# ---------------------------------------------------------------- script
def beats(ep: layout.Episode) -> list[dict]:
    e = ep.load("episode.json")
    out = []
    for n in e["narration"]:
        _, front, body = (ep.dir / n["beat"]).read_text(encoding="utf-8").split("---", 2)
        meta = dict(line.split(": ", 1) for line in front.strip().splitlines())
        out.append({"id": meta["beat"], "body": body.strip(), "planned_s": int(meta["end"]) - int(meta["start"])})
    return out


def spoken(text: str, glossary: list[dict]) -> str:
    for g in glossary:
        if g["say"] == "letter by letter":
            text = re.sub(rf"\b{re.escape(g['term'])}\b", "-".join(g["term"]), text)
        elif re.fullmatch(r"[A-Z]{2}-\d+", g["term"]):
            text = text.replace(g["term"], g["say"])
    return text


def prompt(beat: dict, episode: dict, pace: str = "") -> str:
    """The full request for one beat: style, pronunciations, then the directed lines."""
    glossary = episode.get("pronunciations", [])
    lines: list[str] = []
    for raw in beat["body"].splitlines():
        raw = raw.strip()
        if not raw:
            continue
        tags: list[str] = []
        m = re.match(r"^\[([^\]]+)\]\s*", raw)
        if m:
            tags = [t.strip() for t in m.group(1).split(",")]
            raw = raw[m.end():]
        # A pause is an ellipsis in the text, never a word: the model reads "(pause)" aloud.
        lead = ""
        if "beat" in tags:
            tags = [t for t in tags if t != "beat"]
            lead = "… "
            if not raw:
                if lines:
                    lines[-1] += " …"
                continue
        raw = TAG.sub(lambda mm: " … " if mm.group(1).strip() == "beat" else
                      " (" + ", ".join(DIRECTION.get(t.strip(), t.strip()) for t in mm.group(1).split(",")) + ") ", raw)
        note = ", ".join(DIRECTION.get(t, t) for t in tags) or "energetic"
        lines.append(f"({note}) {lead}{spoken(raw.strip(), glossary)}")
    say = [f"{g['term']} as '{g['say']}'" for g in glossary
           if g["say"] != "letter by letter" and not re.fullmatch(r"[A-Z]{2}-\d+", g["term"]) and g["term"] in beat["body"]]
    pron = ("\nPronounce " + "; ".join(say) + ".") if say else ""
    style = episode.get("voice_style") or DEFAULT_STYLE
    return style + READ_RULES + PACE.get(pace, "") + pron + "\n\n" + "\n".join(lines)


def plain(beat: dict, episode: dict) -> str:
    """The words only, for voices that cannot take direction."""
    text = TAG.sub(lambda mm: " … " if mm.group(1).strip() == "beat" else " ", beat["body"])
    return spoken(" ".join(text.split()), episode.get("pronunciations", []))


# ---------------------------------------------------------------- providers
def _request(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # The status code stays in the message: KeyRing rotates on 429 and quota errors.
        raise RuntimeError(f"provider error {e.code}: {e.read()[:500].decode(errors='replace')}") from e


def _tts_body(text: str, voice: str) -> dict:
    return {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }


def call_gemini_api(model: str, voice: str, text: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    return keys.run_with_keys("GEMINI_API_KEY", lambda key: _request(url, _tts_body(text, voice), {"x-goog-api-key": key}))


def call_vertex(model: str, voice: str, text: str) -> dict:
    proj = providers.setting("voice", "vertex_project")
    loc = providers.setting("voice", "vertex_location", "us-central1")
    if not proj:
        raise SystemExit("vertex needs a project: animative providers set voice vertex --vertex_project <id>")
    gcloud = shutil.which("gcloud")
    if not gcloud:
        raise SystemExit("gcloud not found on PATH")
    tok = subprocess.run([gcloud, "auth", "application-default", "print-access-token"],
                         capture_output=True, text=True, check=True).stdout.strip()
    host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
    url = f"https://{host}/v1/projects/{proj}/locations/{loc}/publishers/google/models/{model}:generateContent"
    return _request(url, _tts_body(text, voice), {"Authorization": f"Bearer {tok}", "x-goog-user-project": proj})


def _write_pcm(res: dict, dest: Path) -> tuple[float, str]:
    part = res["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    m = re.search(r"rate=(\d+)", part.get("mimeType", "rate=24000"))
    rate = int(m.group(1)) if m else 24000
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return len(pcm) / 2 / rate, part.get("mimeType", "")


def to_wav(src: Path, dest: Path) -> float:
    """Any audio file to 48 kHz mono wav; returns its length in seconds."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "48000", str(dest)], check=True)
    with wave.open(str(dest), "rb") as w:
        return w.getnframes() / w.getframerate()


def _kokoro(text: str, voice: str, dest: Path) -> None:
    """Local Kokoro: American English pipeline, 24 kHz. Needs the kokoro extra."""
    try:
        import numpy as np
        import soundfile as sf  # type: ignore[import-not-found]
        from kokoro import KPipeline  # type: ignore[import-not-found]
    except ImportError as e:
        raise SystemExit("kokoro is not installed: uv tool install 'animative[kokoro]'") from e
    chunks = [audio for _gs, _ps, audio in KPipeline(lang_code="a")(text, voice=voice)]
    sf.write(str(dest), np.concatenate(chunks) if chunks else np.zeros(24000, dtype=np.float32), 24000)


def tier(model: str) -> str:
    return "pro" if "pro" in model else "flash"


def record_one(ep: layout.Episode, beat: dict, use: str, model: str, voice: str, pace: str = "") -> Path:
    """One take of one beat. A take that fails leaves nothing behind, so it is never mistaken for one."""
    try:
        return _record_one(ep, beat, use, model, voice, pace)
    except BaseException:
        stem_glob = f"{beat['id']}--{voice.lower()}--*"
        for f in ep.takes.glob(stem_glob):
            if not f.with_suffix(".json").exists() or f.suffix == ".mp3":
                f.unlink(missing_ok=True)
        raise


def _record_one(ep: layout.Episode, beat: dict, use: str, model: str, voice: str, pace: str = "") -> Path:
    episode = ep.load("episode.json")
    out = ep.takes
    out.mkdir(parents=True, exist_ok=True)
    n = len(list(out.glob(f"{beat['id']}--*.wav"))) + 1
    stem = f"{beat['id']}--{voice.lower()}--{n:02d}"
    wav = out / f"{stem}.wav"
    rec: dict = {"beat": beat["id"], "provider": use, "model_requested": model, "voice": voice,
                 "pace": pace or "default", "created_at": datetime.now(UTC).isoformat(timespec="seconds")}
    if use in ("gemini-api", "vertex"):
        text = prompt(beat, episode, pace)
        res = (call_gemini_api if use == "gemini-api" else call_vertex)(model, voice, text)
        seconds, mime = _write_pcm(res, wav)
        usage = res.get("usageMetadata", {})
        p = PRICES[tier(model)]
        rec.update({"prompt": text, "model_served": res.get("modelVersion"), "response_id": res.get("responseId"),
                    "usage": usage, "mime": mime, "seconds": seconds,
                    "cost_usd": round((usage.get("promptTokenCount", 0) * p["in"]
                                       + usage.get("candidatesTokenCount", 0) * p["out"]) / 1e6, 5)})
    elif use == "edge":
        try:
            import edge_tts  # type: ignore[import-not-found]
        except ImportError as e:
            raise SystemExit("edge-tts is not installed: uv tool install 'animative[edge]'") from e

        text = plain(beat, episode)
        mp3 = wav.with_suffix(".mp3")
        asyncio.run(edge_tts.Communicate(text, voice).save(str(mp3)))
        rec.update({"prompt": text, "model_served": "edge-tts", "seconds": to_wav(mp3, wav), "cost_usd": 0})
        mp3.unlink()
    elif use == "kokoro":
        text = plain(beat, episode)
        raw = wav.with_suffix(".kokoro.wav")
        _kokoro(text, voice, raw)
        rec.update({"prompt": text, "model_served": "kokoro", "seconds": to_wav(raw, wav), "cost_usd": 0})
        raw.unlink()
    else:
        raise SystemExit(f"voice provider {use!r} records through a browser or by hand: "
                         f"animative import {ep.slug} voice <beat> <file> --via {use}")
    wav.with_suffix(".json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"{stem}: {rec['seconds']:.1f} s, {rec.get('model_served')}, ${rec.get('cost_usd', 0)}")
    return wav


def chosen_voice() -> tuple[str, str, str]:
    use = providers.chosen("voice")
    if not use:
        raise SystemExit("no voice chosen yet: animative providers   (Claude asks on first run)")
    d = DEFAULTS.get(use, {"model": use, "voice": "narrator"})
    return use, providers.setting("voice", "model", d["model"]), providers.setting("voice", "voice", d["voice"])


def record(ep: layout.Episode, only: list[str], pace: str = "") -> None:
    use, model, voice = chosen_voice()
    if use in ("gemini-api", "vertex") and (not re.search(r"\d", model) or model.endswith("-latest")):
        raise SystemExit(f"refusing a moving alias: {model}. Name an exact model.")
    for b in beats(ep):
        if not only or b["id"] in only:
            record_one(ep, b, use, model, voice, pace)


def estimate(ep: layout.Episode, takes_per_beat: int = 1) -> float:
    use, model, _ = chosen_voice()
    if use not in ("gemini-api", "vertex"):
        print(f"estimate: {use} costs nothing per take")
        return 0.0
    episode = ep.load("episode.json")
    total = 0.0
    p = PRICES[tier(model)]
    for b in beats(ep):
        tin = len(prompt(b, episode)) / 4 + 1
        # shouts and pauses run long: budget 1.5x the planned seconds of audio
        tout = b["planned_s"] * 1.5 * AUDIO_TOKENS_PER_S
        total += takes_per_beat * (tin * p["in"] + tout * p["out"]) / 1e6
    print(f"estimate: {use} {model}, {takes_per_beat} take(s) per beat, ${total:.3f}")
    return total


def show_prompts(ep: layout.Episode, only: list[str]) -> None:
    episode = ep.load("episode.json")
    for b in beats(ep):
        if not only or b["id"] in only:
            print(f"--- {b['id']}\n{prompt(b, episode)}\n")
