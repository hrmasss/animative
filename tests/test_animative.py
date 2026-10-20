"""animative end to end without media, keys or network: a synthetic character is
drawn, cut, inspected and bundled, and the bundled example plans and times."""

from __future__ import annotations

import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from animative import build, cli, config, keys, layout, providers, rig, voice

SKIN, DARK, RED, WHITE = (240, 175, 130, 255), (35, 35, 40, 255), (200, 50, 60, 255), (250, 250, 250, 255)


def draw_sheet(path: Path) -> None:
    """Three blank-faced poses on top, four eyes and three mouths in a parts row below."""
    img = Image.new("RGBA", (900, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(3):
        cx = 150 + i * 300
        d.ellipse([cx - 45, 20, cx + 45, 70], fill=DARK)                 # hair
        d.ellipse([cx - 40, 40, cx + 40, 130], fill=SKIN)                # face
        d.rectangle([cx - 40, 100, cx + 40, 150], fill=DARK)             # beard from y=100
        d.rectangle([cx - 35, 150, cx + 35, 330], fill=DARK)             # body
        d.rectangle([cx - 30, 330, cx + 30, 400], fill=(60, 60, 90, 255))  # legs
    for i in range(4):
        cx = 60 + i * 100
        d.ellipse([cx - 22, 470, cx + 22, 510], fill=WHITE, outline=DARK, width=3)
        d.ellipse([cx - 8, 482, cx + 8, 498], fill=DARK)
    for i in range(3):
        cx = 540 + i * 120
        d.ellipse([cx - 35, 470 + i * 3, cx + 35, 500 + i * 8], fill=RED, outline=DARK, width=3)
    img.save(path)


RIG = {
    "id": "tester",
    "sources": {"sheet": "sources/sheet.png"},
    "groups": [
        {"kind": "pose", "source": "sheet", "box": [0, 0, 900, 420], "rows": 1, "min_area": 2000,
         "items": ["stand", "point", "wave"]},
        {"kind": "eye", "source": "sheet", "box": [0, 440, 450, 560], "rows": 1, "min_area": 50,
         "items": ["open-l", "open-r", "wide", "closed"]},
        {"kind": "mouth", "source": "sheet", "box": [450, 440, 900, 560], "rows": 1, "min_area": 50,
         "items": ["rest", "talk", "shout"]},
    ],
    "face": {"eye_ref": "open-l", "eye_width": 0.36, "eye_dx": 0.22, "eye_y": 0.56, "mouth_ref": "rest",
             "mouth_width": 0.42, "mouth_y": 0.02, "nose": "rest", "nose_width": 0.0, "nose_y": 0.6,
             "blink": "closed", "shout_mouth": "shout"},
    "expressions": {"neutral": {"pose": "stand", "eyes": ["open-l", "open-r"], "mouth": "rest"},
                    "happy": {"pose": "wave", "eyes": ["closed", "mirror"], "mouth": "talk"}},
    "visemes": {k: {"mouth": "talk"} for k in ("MBP", "AI", "E", "O", "U", "FV", "L", "etc", "open")}
               | {"rest": {"mouth": "rest"}},
}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A workspace with one synthetic host, and provider choices in a temp config folder."""
    monkeypatch.setenv("ANIMATIVE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ANIMATIVE_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("ANIMATIVE_CACHE", str(tmp_path / "cache"))
    cli.main(["init", str(tmp_path / "ws")])
    char = config.characters_dir() / "tester"
    (char / "sources").mkdir(parents=True)
    draw_sheet(char / "sources" / "sheet.png")
    (char / "rig.json").write_text(json.dumps(RIG), encoding="utf-8")
    return tmp_path / "ws"


def test_cut_finds_every_piece_and_each_face(ws):
    lock = rig.cut("tester")
    kinds: dict[str, int] = {}
    for p in lock["parts"].values():
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    assert kinds == {"pose": 3, "eye": 4, "mouth": 3}
    for name in ("stand", "point", "wave"):
        x0, _, x1, _ = lock["parts"][name]["face"]["box"]
        assert 70 <= x1 - x0 <= 90, name             # the 80 px face
        assert abs(lock["parts"][name]["face"]["beard_y"] - (100 - lock["parts"][name]["at"][1])) <= 3, name


def test_cut_refuses_a_miscounted_group(ws):
    bad = json.loads(json.dumps(RIG))
    bad["groups"][0]["items"] = ["stand", "point"]
    (config.characters_dir() / "tester" / "rig.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="found 3 pieces"):
        rig.cut("tester")


def test_a_bundle_is_used_until_the_rig_changes(ws):
    rig.cut("tester", bundle=True)
    assert layout.bundle_is_fresh("tester")
    assert layout.character_cut_dir("tester") == layout.bundled_cut_dir("tester")
    changed = dict(RIG, summary="edited")
    (config.characters_dir() / "tester" / "rig.json").write_text(json.dumps(changed), encoding="utf-8")
    assert not layout.bundle_is_fresh("tester")
    assert layout.ensure_cut("tester") == config.cache_dir() / "characters" / "tester"


def test_inspect_and_the_model_sheet(ws):
    pngs = rig.inspect("tester")
    assert len(pngs) == 1 and pngs[0].exists()
    boxes = json.loads(pngs[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert len(boxes) >= 10
    page = rig.sheet("tester").read_text(encoding="utf-8")
    assert '"id":"tester"' in page


def test_new_character_scaffolds_a_valid_rig(ws):
    cli.main(["character", "new", "rumi"])
    rigj = json.loads((config.characters_dir() / "rumi" / "rig.json").read_text(encoding="utf-8"))
    assert rigj["id"] == "rumi"
    assert set(rigj["visemes"]) - {"_"} == {"rest", "MBP", "AI", "E", "O", "U", "FV", "L", "etc", "open"}


def test_example_plays_with_any_host(ws):
    rig.cut("tester")
    cli.main(["new", "drones", "--from", "drone-war", "--character", "tester"])
    ep = build.Ep("drones")
    assert ep.character == "tester"
    timing = build.cmd_timing(ep)
    shots = timing["shots"]
    assert len(shots) == 38 and shots[0]["f0"] == 0
    assert all(a["f1"] == b["f0"] for a, b in pairwise(shots))
    # the example's poses were drawn for another host; this one falls back to its own
    shot = next(s for s in ep.episode["shots"] if s.get("presenter"))
    spec = build.presenter_spec(ep, shot, 0, 90, [], {}, shot["id"])
    assert spec is not None and spec["pose"].endswith(("stand.png", "wave.png", "point.png"))


def test_voice_prompt_directs_but_never_speaks_a_stage_note(ws):
    cli.main(["new", "drones", "--from", "drone-war"])
    ep = layout.Episode("drones")
    beats = {b["id"]: b for b in voice.beats(ep)}
    text = voice.prompt(beats["hunters"], ep.load("episode.json"))
    assert "(SHOUT it" in text
    assert "(pause)" not in text and "[beat]" not in text
    assert "combat drones" in text


def test_provider_choices_persist_per_person(ws):
    assert providers.missing() == list(providers.CAPABILITIES)
    providers.set_choice("voice", "vertex", vertex_project="demo")
    assert providers.chosen("voice") == "vertex"
    assert providers.setting("voice", "vertex_project") == "demo"
    assert config.choices_file().parent == Path(config.user_config_dir())
    with pytest.raises(SystemExit):
        providers.set_choice("voice", "no-such-voice")


def test_keys_rotate_on_quota_and_stop_on_anything_else(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a,b")
    monkeypatch.setenv("GEMINI_API_KEY_1", "b")
    assert keys.read_keys("GEMINI_API_KEY") == ["a", "b"]
    seen: list[str] = []

    def call(k: str) -> str:
        seen.append(k)
        if k == "a":
            raise RuntimeError("provider error 429: quota")
        return "ok:" + k

    assert keys.run_with_keys("GEMINI_API_KEY", call, sleep=lambda _s: None) == "ok:b"
    assert seen == ["a", "b"]
    with pytest.raises(ValueError):
        keys.run_with_keys("GEMINI_API_KEY", lambda _k: (_ for _ in ()).throw(ValueError("bad request")))


def test_visemes_close_the_lips_on_m_b_p():
    assert build.visemes("mob")[0] == "MBP"
    assert build.visemes("show") == ["etc", "O"]


def test_building_never_loads_scipy():
    """scipy is only for cutting; a bundled host builds without it."""
    code = "import sys, animative.cli, animative.build, animative.voice; print('scipy' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
