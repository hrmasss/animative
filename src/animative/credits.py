"""Write ``episode/credits.md``: every source the cut uses, ready for the description.

Reads the shots' sources from ``episode.json`` (only those ``edit.json`` actually
places), the license proofs saved beside the media in ``assets/sources/licenses/``,
the effects index in ``assets/sound/index.json``, the voice takes' sidecars, any
generated stills' sidecars, and the fonts in the kit. CC BY and CC BY-SA entries
carry title, author, source and license link, as those licenses require.

    animative credits <slug>
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from animative import layout, providers

LICENSE_URL = {
    "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
}


def proof_title(proofs: Path, file: str) -> str | None:
    p = proofs / (Path(file).stem + ".txt")
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8")
    m = re.search(r"^File: File:(.+)$", t, re.M) or re.search(r"^Title: (.+)$", t, re.M)
    return m.group(1).strip() if m else None


def _voice_line(ep: layout.Episode) -> str:
    models = set()
    for side in ep.takes.glob("*.json") if ep.takes.is_dir() else []:
        if side.name == "report.json":
            continue
        rec = json.loads(side.read_text(encoding="utf-8"))
        models.add(f"{rec.get('provider')} ({rec.get('model_served') or rec.get('model_requested')})")
    return ("Narration generated with " + ", ".join(sorted(models)) + ".") if models else "Narration: none recorded yet."


def write(slug: str) -> Path:
    ep = layout.Episode(slug)
    episode = ep.load("episode.json")
    edit = ep.load("edit.json")
    used = {k: v for k, v in edit.get("sources", {}).items() if not k.startswith("gen:")}
    by_url: dict[str, dict] = {}
    for s in episode["shots"]:
        src = s.get("source") or {}
        if not src.get("url") or s["id"] not in used:
            continue
        e = by_url.setdefault(src["url"], {"shots": [], "src": src, "file": used[s["id"]]["file"], "what": s["what"]})
        e["shots"].append(s["id"])
    # sources the edit adds on top of the shot list (a second clip for a shot) carry their own credit
    for k, v in used.items():
        if v.get("url") and v["url"] not in by_url and any(
                seg.get("source") == k for sh in edit.get("shots", {}).values() for seg in sh.get("bg", [])):
            by_url[v["url"]] = {"shots": [k], "src": v, "file": v["file"], "what": v.get("title", k)}
    proofs = ep.assets / "sources" / "licenses"
    pd = [e for e in by_url.values() if e["src"]["license"] == "PD"]
    cc = [e for e in by_url.values() if e["src"]["license"] != "PD"]
    out = [f"# Credits — {episode.get('title', ep.slug)}", "",
           "Ready to paste into the description. Every sourced picture is public domain or Creative Commons.", "",
           "## Footage and photographs", "", "### Creative Commons", ""]
    for e in sorted(cc, key=lambda e: e["shots"][0]):
        lic = e["src"]["license"]
        title = proof_title(proofs, e["file"]) or e["what"]
        sa = (" Adapted (cropped, moved, graded) for this video; the adaptation is shared under the same license."
              if "SA" in lic else " Cropped, moved and graded for this video.")
        out.append(f"- **{title}** by {e['src']['credit']}, {lic} ({LICENSE_URL.get(lic, '')}). "
                   f"Source: {e['src']['url']}.{sa}")
    out += ["", "### Public domain", "", "Credit given as a courtesy.", ""]
    for e in sorted(pd, key=lambda e: e["shots"][0]):
        title = proof_title(proofs, e["file"]) or e["what"]
        out.append(f"- {title}: {e['src']['credit']}. {e['src']['url']}")
    if any("dvidshub" in e["src"]["url"] or "U.S." in e["src"]["credit"] for e in pd):
        out += ["", "U.S. military imagery does not imply endorsement by the Department of Defense."]
    gen = sorted((ep.assets / "generated").rglob("*.json")) if (ep.assets / "generated").is_dir() else []
    if gen:
        tools = sorted({json.loads(g.read_text(encoding="utf-8")).get("tool", "?") for g in gen})
        out += ["", "## Generated illustration", "",
                f"{len(gen)} illustration stills or clips made with {', '.join(tools)}. "
                "Illustration only, never presented as footage of a real event."]
    out += ["", "## Sound effects", ""]
    index = ep.assets / "sound" / "index.json"
    for s in json.loads(index.read_text(encoding="utf-8")) if index.exists() else []:
        out.append(f"- {s['name']}: {s.get('author', '')}, {s.get('source_url', '')} ({s.get('license', 'CC0')})")
    music = providers.chosen("music")
    out += ["", "## Music", "",
            "Original music bed generated offline for this video. No third-party samples." if music in (None, "builtin")
            else f"Music from {music}; see the license proof in assets/sound/licenses/.",
            "", "## Voice", "", _voice_line(ep), "", "## Maps and fonts", "",
            "- Country shapes: Natural Earth, public domain. https://www.naturalearthdata.com/",
            "- Anton and Inter fonts, SIL Open Font License 1.1.", "", "## Fact sources", ""]
    for f in ep.load("facts.json") or []:
        if f.get("source"):
            out.append(f"- {f['claim']}: {f['source']}")
    dest = ep.dir / "credits.md"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"credits: {len(cc)} CC, {len(pd)} PD -> {dest}")
    return dest
