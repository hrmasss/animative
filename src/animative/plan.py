#!/usr/bin/env python
"""Render an episode's script and shot plan as one page to read and approve.

The episode directory is the source: ``episode.json`` holds the shots and
``beats/*.md`` hold every spoken word. This page is derived from them and lands
in ``projects/<slug>/build/plan.html``; it is never edited by hand. Optional
``facts.json`` beside the episode adds the fact-check table.

    animative plan <slug>
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from animative import layout

TAG = re.compile(r"\[([^\]]+)\]")


def read_beat(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    meta = dict(line.split(": ", 1) for line in front.strip().splitlines())
    return {"id": meta["beat"], "start": int(meta["start"]), "end": int(meta["end"]), "body": body.strip()}


def words(body: str) -> int:
    return len(TAG.sub("", body).split())


def tc(s: int) -> str:
    return f"{s // 60}:{s % 60:02d}"


def esc(s) -> str:
    return html.escape(str(s))


def script_html(body: str) -> str:
    out = []
    for line in body.splitlines():
        if not line.strip():
            continue
        line = esc(line)
        line = TAG.sub(lambda m: f'<span class="dir">{m.group(1)}</span>', line)
        out.append(f"<p>{line}</p>")
    return "\n".join(out)


def on_screen(s: dict) -> str:
    bits = []
    g = s.get("graphic")
    if g:
        d = g["data"]
        card = d.get("card") or (d if g["component"] == "name-card" else None)
        label = g["component"].replace("-", " ")
        if card:
            bits.append(f'<b>{esc(card["name"])}</b> · {esc(card["country"])} · {esc(card["maker"])} · {esc(card.get("year_means", ""))} {esc(card["year"])}')
            if g["component"] != "name-card":
                bits.append(esc(label))
        elif "text" in d:
            bits.append(f'{esc(label)}: <b>{esc(d["text"])}</b>')
        elif "name" in d:
            bits.append(f'{esc(label)}: {esc(d["name"])}')
        else:
            bits.append(esc(label))
    p = s.get("presenter")
    if p:
        bits.append(f'<span class="host">host</span> {esc(p["pose"])} · {esc(p["feeling"])} · {esc(p["placement"])}')
    return "<br>".join(bits) or '<span class="muted">none</span>'


def source_html(s: dict) -> str:
    src = s.get("source")
    if not src:
        return '<span class="muted">rendered</span>'
    if src.get("url"):
        lic = f' <span class="lic">{esc(src.get("license", ""))}</span>' if src.get("license") else ""
        return f'<a href="{esc(src["url"])}">{esc(src.get("credit") or src["want"])}</a>{lic}'
    return f'<span class="muted">find:</span> {esc(src["want"])}'


def build(episode: str) -> Path:
    ep_dir = layout.Episode(episode).dir
    ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    beats = [read_beat(ep_dir / n["beat"]) for n in ep["narration"]]
    facts_path = ep_dir / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else []
    shots = ep["shots"]
    total = beats[-1]["end"]
    nwords = sum(words(b["body"]) for b in beats)
    kinds = {k: sum(1 for s in shots if s["kind"] == k) for k in ("archival", "still_motion", "graphic")}

    strip = "".join(
        f'<a class="seg" href="#{b["id"]}" style="flex:{b["end"] - b["start"]}">'
        f'<span>{esc(b["id"].replace("-", " "))}</span><small>{tc(b["start"])}</small></a>'
        for b in beats
    )
    sections = []
    for b in beats:
        rows = "".join(
            f'<tr><td class="tc">{tc(s["start"])}–{tc(s["end"])}</td>'
            f'<td><span class="kind k-{s["kind"]}">{s["kind"].replace("_", " ")}</span></td>'
            f'<td>{esc(s["what"])}</td>'
            f'<td class="cam">{esc(" · ".join(x for x in (s.get("size"), s.get("angle"), s.get("movement")) if x)) or "—"}</td>'
            f'<td>{on_screen(s)}</td>'
            f'<td class="sfx">{esc(", ".join(s.get("sfx", [])))}</td>'
            f'<td>{source_html(s)}</td></tr>'
            for s in shots if s["beat"] == b["id"]
        )
        sections.append(f"""
<section class="beat" id="{b["id"]}">
  <div class="beat-head"><span class="tc">{tc(b["start"])}–{tc(b["end"])}</span><h3>{esc(b["id"].replace("-", " ").capitalize())}</h3><span class="muted">{words(b["body"])} words</span></div>
  <div class="vo">{script_html(b["body"])}</div>
  <div class="tablewrap"><table>
    <thead><tr><th>Time</th><th>Kind</th><th>Picture</th><th>Camera</th><th>On screen</th><th>Sound</th><th>Source</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>""")

    gloss = "".join(f'<tr><td>{esc(p["term"])}</td><td>{esc(p["say"])}</td></tr>' for p in ep["pronunciations"])
    always = "".join(f'<li><b>{esc(a["component"].replace("-", " "))}</b>: {esc(", ".join(f"{k} {v}" for k, v in a["data"].items()))}</li>' for a in ep["always_on"])
    rules = "".join(f"<li>{esc(r)}</li>" for r in ep["motion_rules"])
    fact_rows = "".join(
        f'<tr><td>{esc(f["claim"])}</td><td><span class="pill {"ok" if f["verdict"] == "TRUE" else "fix"}">{esc(f["verdict"].lower())}</span></td>'
        f'<td>{esc(f.get("note", ""))}</td><td>{f'<a href="{esc(f["source"])}">source</a>' if f.get("source") else '<span class="muted">none yet</span>'}</td></tr>'
        for f in facts
    )
    facts_html = (
        f'<div class="tablewrap"><table><thead><tr><th>Claim</th><th>Verdict</th><th>Note</th><th></th></tr></thead><tbody>{fact_rows}</tbody></table></div>'
        if facts else '<p class="muted">No fact-check recorded yet.</p>'
    )
    decisions = "".join(
        f'<li><b>{esc(d["ask"])}</b><br><span class="muted">{esc(d["why"])}</span><br>Recommended: {esc(d["recommend"])}</li>'
        for d in ep.get("open_decisions", [])
    )
    steps = "".join(f"<li>{esc(s)}</li>" for s in ep.get("production", []))

    page = TEMPLATE.format(
        title=esc(ep["title"]), ep_id=esc(ep["id"]), runtime=tc(total), nshots=len(shots), nwords=nwords,
        archival=kinds["archival"], still=kinds["still_motion"], graphic=kinds["graphic"],
        host=sum(1 for s in shots if s.get("presenter")), strip=strip, sections="".join(sections),
        gloss=gloss, always=always, rules=rules, facts=facts_html, decisions=decisions or "<li>None open.</li>",
        steps=steps, episode=esc(episode), summary=esc(ep.get("summary", "")),
    )
    out = layout.Episode(episode).root / "build" / "plan.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


TEMPLATE = """<meta charset="utf-8">
<title>{title} Plan</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* Layout: a production rundown. Decisions first, then the run of show as a strip, then each
   beat as script over its shot table, then the reference material. */
:root {{
  --paper: #f3f2ef; --sheet: #ffffff; --ink: #1c1b19; --muted: #66625b; --line: #dcd8d0;
  --signal: #c2410c; --signal-soft: #fbe6da; --archival: #2f5d8a; --still: #6b5b95; --graphic: #2f7d5b;
  --display: "Bricolage Grotesque", "Avenir Next", "Segoe UI", sans-serif;
  --body: "Public Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper: #121110; --sheet: #1b1a18; --ink: #ece9e3; --muted: #a39e95; --line: #2f2d29;
    --signal: #ff8a4c; --signal-soft: #3a2216; --archival: #7fb2e5; --still: #b9a6e8; --graphic: #7fd1a8; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #121110; --sheet: #1b1a18; --ink: #ece9e3; --muted: #a39e95; --line: #2f2d29;
  --signal: #ff8a4c; --signal-soft: #3a2216; --archival: #7fb2e5; --still: #b9a6e8; --graphic: #7fd1a8; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{ background: var(--paper); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 64px; }}
.wrap {{ max-width: 1240px; margin: 0 auto; display: grid; gap: 44px; }}
h1, h2, h3 {{ font-family: var(--display); margin: 0; line-height: 1.1; text-wrap: balance; }}
h1 {{ font-size: clamp(34px, 6vw, 60px); font-weight: 800; letter-spacing: -0.02em; }}
h2 {{ font-size: 24px; font-weight: 800; }}
h3 {{ font-size: 19px; font-weight: 600; }}
p {{ margin: 0; max-width: 70ch; }}
a {{ color: var(--signal); }}
.eyebrow {{ font-family: var(--mono); font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--signal); }}
.muted {{ color: var(--muted); }}
header {{ display: grid; gap: 12px; border-bottom: 2px solid var(--ink); padding-bottom: 18px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 6px 26px; font-variant-numeric: tabular-nums; }}
.stats span {{ font-family: var(--display); font-weight: 800; font-size: 24px; }}
.stats small {{ color: var(--muted); margin-left: 5px; font-size: 13px; }}
section {{ display: grid; gap: 14px; }}
.decide {{ background: var(--signal-soft); border: 1px solid var(--signal); border-radius: 10px; padding: 18px 20px; display: grid; gap: 10px; }}
.decide ol {{ margin: 0; padding-left: 20px; display: grid; gap: 12px; }}
.strip {{ display: flex; gap: 3px; min-height: 64px; }}
.seg {{ background: var(--sheet); border: 1px solid var(--line); border-radius: 6px; padding: 8px; color: var(--ink); text-decoration: none;
  display: flex; flex-direction: column; justify-content: space-between; min-width: 0; overflow: hidden; }}
.seg:hover {{ border-color: var(--signal); }}
.seg span {{ font-size: 12px; font-weight: 600; text-transform: capitalize; overflow-wrap: anywhere; line-height: 1.2; }}
.seg small {{ font-family: var(--mono); font-size: 11px; color: var(--muted); }}
.beat {{ background: var(--sheet); border: 1px solid var(--line); border-radius: 10px; padding: 18px; gap: 14px; scroll-margin-top: 16px; }}
.beat-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; }}
.tc {{ font-family: var(--mono); font-size: 12.5px; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }}
.vo {{ display: grid; gap: 6px; border-left: 3px solid var(--signal); padding: 4px 0 4px 14px; font-size: 16.5px; }}
.dir {{ font-family: var(--mono); font-size: 11.5px; color: var(--signal); background: var(--signal-soft); border-radius: 4px; padding: 1px 6px; margin-right: 4px; white-space: nowrap; }}
.tablewrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 980px; font-size: 13.5px; }}
th, td {{ text-align: left; vertical-align: top; padding: 8px 10px; border-bottom: 1px solid var(--line); }}
th {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 600; }}
td.cam, td.sfx {{ font-family: var(--mono); font-size: 12px; color: var(--muted); }}
.kind {{ font-family: var(--mono); font-size: 11px; border: 1px solid currentColor; border-radius: 999px; padding: 1px 8px; white-space: nowrap; }}
.k-archival {{ color: var(--archival); }} .k-still_motion {{ color: var(--still); }} .k-graphic {{ color: var(--graphic); }}
.host {{ font-family: var(--mono); font-size: 11px; background: var(--ink); color: var(--paper); border-radius: 4px; padding: 0 5px; }}
.lic {{ font-family: var(--mono); font-size: 11px; color: var(--muted); }}
.pill {{ font-family: var(--mono); font-size: 11px; border-radius: 999px; padding: 1px 8px; border: 1px solid currentColor; white-space: nowrap; }}
.pill.ok {{ color: var(--graphic); }} .pill.fix {{ color: var(--signal); }}
.cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }}
.cols > div {{ min-width: 0; display: grid; gap: 8px; align-content: start; }}
ul, ol {{ margin: 0; padding-left: 20px; }}
li {{ margin-bottom: 4px; }}
.small table {{ min-width: 0; }}
@media (max-width: 640px) {{ .strip {{ flex-wrap: wrap; }} .seg {{ flex: 1 1 30% !important; }} }}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Episode {ep_id} · script and shot plan · for approval</div>
    <h1>{title}</h1>
    <p class="muted">{summary} Timings are planned; the final cut follows the recorded voice.</p>
    <div class="stats">
      <div><span>{runtime}</span><small>planned runtime</small></div>
      <div><span>{nwords}</span><small>words of voice-over</small></div>
      <div><span>{nshots}</span><small>shots</small></div>
      <div><span>{archival}</span><small>archival</small></div>
      <div><span>{still}</span><small>stills in motion</small></div>
      <div><span>{graphic}</span><small>graphics</small></div>
      <div><span>{host}</span><small>host cameos</small></div>
    </div>
  </header>

  <section class="decide">
    <h2>Decide before dispatch</h2>
    <ol>{decisions}</ol>
  </section>

  <section>
    <div class="eyebrow">Run of show</div>
    <nav class="strip">{strip}</nav>
  </section>

  {sections}

  <section>
    <div class="eyebrow">Fact-check</div>
    <h2>Every claim, checked</h2>
    {facts}
  </section>

  <section class="cols">
    <div><h3>Always on screen</h3><ul>{always}</ul></div>
    <div><h3>Motion rules</h3><ul>{rules}</ul></div>
    <div class="small"><h3>Say it right</h3><div class="tablewrap"><table><tbody>{gloss}</tbody></table></div></div>
  </section>

  <section>
    <div class="eyebrow">After approval</div>
    <h2>What runs next</h2>
    <ol>{steps}</ol>
  </section>

  <footer class="muted" style="font-size:13px">Built from <code>projects/{episode}/episode/</code> by <code>animative plan</code>. Edit the episode, not this page.</footer>
</div>
"""

