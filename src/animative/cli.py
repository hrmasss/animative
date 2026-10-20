"""animative: character-hosted explainer videos.

A 2D host cut from generated sprite sheets presents a fast, always-moving
explainer built from public-domain and Creative Commons footage, generated
stills, a directed voice-over, music, effects and kinetic captions. The recipe,
step by step, is the Claude Code skill that ships with this package.

    animative init                                # make this folder a workspace
    animative setup                               # install the render kit (Node), once
    animative doctor                              # tools found, providers chosen
    animative providers [set voice gemini-api --voice Fenrir]
    animative character new rumi                  # a host: sheets go in characters/rumi/sources/
    animative inspect rumi                        # number every piece on its sheets
    animative cut rumi [--bundle]                 # cut it; --bundle keeps parts beside the rig
    animative sheet rumi                          # the model sheet: every pose, every feeling
    animative new my-video [--from drone-war] [--character rumi]
    animative list
    animative plan my-video                       # the script and shot plan as one page
    animative voice my-video estimate|prompt|record [beat ...]
    animative takes my-video                      # score takes against the script
    animative stills my-video [id ...]            # agy image provider
    animative music my-video                      # builtin music bed
    animative import my-video still s05 ~/Downloads/x.png --via chatgpt-web
    animative draft my-video [timing|compose|render|mix|assemble]
    animative pin my-video --by <name> --via "approved the draft"
    animative final my-video
    animative credits my-video
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from animative import __version__, config, layout, providers


def cmd_doctor(_: argparse.Namespace) -> int:
    def tool(name: str) -> str:
        return "found" if shutil.which(name) else "MISSING"

    print("tools")
    for t, why in [("node", "HyperFrames renders through Node 22+"), ("npx", "runs HyperFrames"),
                   ("ffmpeg", "media prep, mix and assembly"), ("ffprobe", "durations and frame counts"),
                   ("docker", "optional: pinned, identical renders")]:
        print(f"  {t:<8} {tool(t):<8} {why}")
    kit = layout.kit_dir() / "node_modules" / "hyperframes"
    print(f"  kit      {'found' if kit.exists() else 'MISSING':<8} animative setup")
    try:
        import scipy  # noqa: F401
        print("  scipy    found    character cutting")
    except ImportError:
        print("  scipy    MISSING  needed only to cut a character")
    print("\ncharacters")
    for name in layout.list_characters():
        if layout.bundle_is_fresh(name):
            state = "ready (bundled parts)"
        elif (layout.character_cut_dir(name) / "rig.lock.json").exists():
            state = "cut (cache)"
        else:
            state = f"not cut yet (animative cut {name})"
        print(f"  {name:<10} {state}")
    gaps = providers.missing()
    print("\nproviders" + (f"  (not chosen yet: {', '.join(gaps)})" if gaps else ""))
    print(providers.report())
    return 0


def cmd_providers(a: argparse.Namespace) -> int:
    if a.action == "set":
        settings = dict(zip(a.rest[0::2], a.rest[1::2], strict=False))
        providers.set_choice(a.capability, a.choice, **{k.lstrip("-"): v for k, v in settings.items()})
    print(providers.report())
    return 0


def cmd_new(a: argparse.Namespace) -> int:
    ep = layout.Episode(a.slug)
    if ep.exists():
        raise SystemExit(f"{ep.dir} already exists")
    src = config.EXAMPLES_DIR / (a.from_ or "_blank")
    if not (src / "episode.json").exists():
        known = [d.name for d in config.EXAMPLES_DIR.iterdir() if (d / "episode.json").exists()]
        raise SystemExit(f"no example {a.from_!r}. Examples: {', '.join(known)}")
    shutil.copytree(src, ep.dir, ignore=shutil.ignore_patterns("README.md", "credits.md"))
    hosts = layout.list_characters()
    host = a.character or (hosts[0] if len(hosts) == 1 else None)
    epj = ep.dir / "episode.json"
    data = json.loads(epj.read_text(encoding="utf-8"))
    data["character"] = host or "host"
    epj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for d in (ep.assets / "inbox", ep.assets / "sources" / "licenses", ep.assets / "sound" / "licenses", ep.videos):
        d.mkdir(parents=True, exist_ok=True)
    print(f"Created {ep.root}")
    print("  episode/   <- the script (beats/), the shot plan (episode.json), the edit (edit.json)")
    print("  assets/    <- sources, voice takes, sound, generated stills; inbox/ for dropped files")
    print("  videos/    <- the draft and the final")
    if not host:
        print("No host chosen yet: make one (animative character new <name>), then set \"character\" in episode.json.")
    return 0


def cmd_init(a: argparse.Namespace) -> int:
    root = Path(a.dir).resolve()
    (root / config.MARKER).mkdir(parents=True, exist_ok=True)
    for d in ("characters", "projects"):
        (root / d).mkdir(exist_ok=True)
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text("# animative workspace: authored files are tracked, gathered and built media is not\n"
                      ".env\n.animative/cache/\nprojects/*/assets/\nprojects/*/build/\nprojects/*/videos/\n",
                      encoding="utf-8")
    print(f"workspace: {root}")
    print("  characters/  <- hosts (animative character new <name>)")
    print("  projects/    <- videos (animative new <slug>)")
    print("  .env         <- API keys such as GEMINI_API_KEY, if a provider needs one")
    return 0


def cmd_setup(_: argparse.Namespace) -> int:
    """Install the render kit's Node packages (HyperFrames, GSAP) at their pinned versions."""
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm not found: install Node 22+ first")
    dest = config.kit_install_dir()
    dest.mkdir(parents=True, exist_ok=True)
    for f in ("package.json", "package-lock.json"):
        shutil.copy2(config.KIT_SRC / f, dest / f)
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=dest, check=True)
    print(f"render kit ready: {dest}")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    eps = layout.list_episodes()
    if not eps:
        print("No projects yet. Start one: animative new my-video")
    for ep in eps:
        e = ep.load("episode.json")
        have = [p.name for p in (ep.videos.glob("*.mp4") if ep.videos.is_dir() else [])]
        print(f"{ep.slug:<24} {e.get('title', ''):<32} {len(e.get('shots', []))} shots  {', '.join(have) or 'not built'}")
    return 0


def cmd_cut(a: argparse.Namespace) -> int:
    from animative import rig
    rig.cut(a.character, bundle=a.bundle)
    if a.bundle:
        rig.sheet(a.character)
    return 0


def cmd_inspect(a: argparse.Namespace) -> int:
    from animative import rig
    rig.inspect(a.character, a.min_area)
    return 0


def cmd_character(a: argparse.Namespace) -> int:
    d = layout.character_dir(a.name)
    if d.exists():
        raise SystemExit(f"{d} already exists")
    (d / "sources").mkdir(parents=True)
    template = config.TEMPLATE_CHARACTER
    for f in ("rig.json", "README.md"):
        text = (template / f).read_text(encoding="utf-8").replace("<name>", a.name)
        (d / f).write_text(text, encoding="utf-8")
    print(f"Created {d}")
    print("  reference.png  <- the base figure (step 1 in README.md)")
    print("  sources/       <- the sprite sheets (step 2)")
    print("  rig.json       <- name every piece (step 3: animative inspect " + a.name + ")")
    return 0


def cmd_sheet(a: argparse.Namespace) -> int:
    from animative import rig
    rig.sheet(a.character)
    return 0


def cmd_plan(a: argparse.Namespace) -> int:
    from animative import plan
    print(plan.build(a.slug))
    return 0


def cmd_voice(a: argparse.Namespace) -> int:
    from animative import voice
    ep = layout.Episode(a.slug)
    if a.action == "estimate":
        voice.estimate(ep, a.takes)
    elif a.action == "prompt":
        voice.show_prompts(ep, a.beats)
    else:
        voice.record(ep, a.beats, a.pace)
    return 0


def cmd_takes(a: argparse.Namespace) -> int:
    from animative import takes
    takes.report(a.slug)
    return 0


def cmd_stills(a: argparse.Namespace) -> int:
    from animative import stills
    stills.generate(a.slug, a.ids, a.accounts.split(",") if a.accounts else None)
    return 0


def cmd_music(a: argparse.Namespace) -> int:
    from animative import music_bed
    music_bed.write(layout.Episode(a.slug).assets / "sound" / "music" / "bed.wav")
    return 0


def cmd_import(a: argparse.Namespace) -> int:
    from animative import inbox
    text = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else None
    inbox.import_file(a.slug, a.kind, a.id, a.file, a.via, text, a.license, a.page)
    return 0


def _build(slug: str, final: bool, step: str) -> int:
    from animative import build
    ep = build.Ep(slug, final=final)
    steps = {"timing": build.cmd_timing, "compose": build.cmd_compose, "mix": build.cmd_mix,
             "assemble": build.cmd_assemble}
    if step == "all":
        build.build_all(ep)
    elif step == "render":
        build.cmd_render(ep, [])
    else:
        steps[step](ep)
    return 0


def cmd_draft(a: argparse.Namespace) -> int:
    return _build(a.slug, False, a.step)


def cmd_final(a: argparse.Namespace) -> int:
    return _build(a.slug, True, a.step)


def cmd_pin(a: argparse.Namespace) -> int:
    from animative import pin
    ep = layout.Episode(a.slug)
    if a.check:
        for beat, take in pin.check(ep).items():
            print(f"{beat}: {take}")
    elif a.beat:
        pin.pin_voice(ep, a.beat, a.take, a.by, a.via)
    else:
        pin.pin_draft(ep, a.by, a.via)
    return 0


def cmd_credits(a: argparse.Namespace) -> int:
    from animative import credits
    credits.write(a.slug)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="animative", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"animative {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("dir", nargs="?", default=".")
    p.set_defaults(fn=cmd_init)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    p = sub.add_parser("providers")
    p.add_argument("action", nargs="?", choices=["show", "set"], default="show")
    p.add_argument("capability", nargs="?")
    p.add_argument("choice", nargs="?")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="--key value settings, e.g. --voice Fenrir")
    p.set_defaults(fn=cmd_providers)
    p = sub.add_parser("new")
    p.add_argument("slug")
    p.add_argument("--from", dest="from_", help="start from an example, e.g. drone-war")
    p.add_argument("--character", help="the host, a folder under characters/")
    p.set_defaults(fn=cmd_new)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("cut")
    p.add_argument("character")
    p.add_argument("--bundle", action="store_true", help="write the parts into the repo, ready to commit")
    p.set_defaults(fn=cmd_cut)
    p = sub.add_parser("sheet")
    p.add_argument("character")
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("inspect")
    p.add_argument("character")
    p.add_argument("--min-area", type=int, default=60)
    p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("character")
    p.add_argument("action", choices=["new"])
    p.add_argument("name")
    p.set_defaults(fn=cmd_character)
    for name, fn in (("plan", cmd_plan), ("takes", cmd_takes), ("music", cmd_music), ("credits", cmd_credits)):
        p = sub.add_parser(name)
        p.add_argument("slug")
        p.set_defaults(fn=fn)
    p = sub.add_parser("voice")
    p.add_argument("slug")
    p.add_argument("action", choices=["estimate", "prompt", "record"])
    p.add_argument("beats", nargs="*")
    p.add_argument("--takes", type=int, default=1)
    p.add_argument("--pace", default="", choices=["", "fast"])
    p.set_defaults(fn=cmd_voice)
    p = sub.add_parser("stills")
    p.add_argument("slug")
    p.add_argument("ids", nargs="*")
    p.add_argument("--accounts")
    p.set_defaults(fn=cmd_stills)
    p = sub.add_parser("import")
    p.add_argument("slug")
    p.add_argument("kind", choices=["voice", "still", "clip", "music", "sfx"])
    p.add_argument("id")
    p.add_argument("file")
    p.add_argument("--via", required=True, help="the provider that made it, e.g. ai-studio-web, chatgpt-web, manual")
    p.add_argument("--prompt-file")
    p.add_argument("--license")
    p.add_argument("--page")
    p.set_defaults(fn=cmd_import)
    for name, fn in (("draft", cmd_draft), ("final", cmd_final)):
        p = sub.add_parser(name)
        p.add_argument("slug")
        p.add_argument("step", nargs="?", default="all", choices=["all", "timing", "compose", "render", "mix", "assemble"])
        p.set_defaults(fn=fn)
    p = sub.add_parser("pin")
    p.add_argument("slug")
    p.add_argument("beat", nargs="?")
    p.add_argument("take", nargs="?")
    p.add_argument("--by", default="")
    p.add_argument("--via", default="")
    p.add_argument("--check", action="store_true")
    p.set_defaults(fn=cmd_pin)

    a = ap.parse_args(argv)
    config.load_env()  # the workspace .env, so its keys count as available
    if a.cmd == "pin" and not a.check and not (a.by and a.via):
        ap.error("pin needs --by and --via: who approved, and how they said it")
    return a.fn(a)


def run() -> None:
    """Console entry point."""
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(f"command failed ({e.returncode}): {' '.join(map(str, e.cmd))[:300]}")


if __name__ == "__main__":
    run()
