# edit.json and the graphics kit

`episode/edit.json` is the cut: which file each shot shows and from where, when things happen,
which effects play. You write it while building the draft. The drone-war example uses every key
below; read it beside this page.

## Anchors

Anything with a time takes an anchor:

| Anchor | Means |
|---|---|
| `"w:Hellfire"` | when that word starts in the voice, inside this shot |
| `"w:Hellfire+0.2"` | 0.2 s after it (`-0.3` before) |
| `0.4` | 0.4 s into the shot |
| `-0.5` | 0.5 s before the shot ends |

## Top level

| Key | Default | Holds |
|---|---|---|
| `beat_gap` | 0.25 | seconds of silence between beats |
| `tail` | 1.5 | seconds after the last word |
| `sfx_gain_db` | -7.5 | the effects bus |
| `render_docker` | false | render in the pinned Docker image |
| `music` | none | `{"file": "sound/music/bed.wav", "lufs": -20, "in": 0, "gain_db": 0}` |
| `voice` | newest take | `{"<beat>": "<take file name>"}` |
| `sources` | | files by shot id, see below; `"gen:<id>"` for generated ones |
| `shots` | | per-shot decisions, see below |
| `sfx_map` | | effect names in `episode.json` → names in `assets/sound/index.json`, or `"SKIP"` |
| `no_ticker` | | shot ids with no year ticker |
| `highlights` | | `{"<name>": ["TUR", "UKR", ...]}`: country codes a `world-map` lights up when its data says `"highlight": "<name>"` |
| `highlight_home` | | `{"<name>": "TUR"}`: the country drawn as home |
| `timeline_extra` | | `[{"year": 1982, "name": "Bekaa decoys", "source": "s10"}]`: timeline entries with no name card |

## sources

```json
"s04": {"file": "sources/s04-abrams.jpg", "url": "...", "license": "PD", "credit": "U.S. Army",
        "in": 12.5, "len": 6, "fit": "cover", "precrop": [0, 0.1, 1, 0.9],
        "crops": [null, [1.7, 28, 45], [1.45, 50, 78]]}
```

`in` is the video in-point and `len` its usable seconds. `precrop` cuts a picture down before
framing, as `[x0, y0, x1, y1]` fractions; use it to keep faces and captions out. `crops` lists the
framings a long hold cycles through, as `[zoom, x%, y%]`; `null` means the full frame.

## shots.<id>

| Key | Holds |
|---|---|
| `cue` | `"w:Word"`: cut to this shot 0.12 s before that word |
| `bg` | segments `[{"source": "s12", "at": 0, "move": "zoom_in", "grade": "punch"}, {"source": "gen:dawn-sky", "at": "w:Ukraine"}]` |
| `graphic_at`, `graphic_until` | when the shot's own graphic (from `episode.json`) enters and leaves |
| `graphic_data` | overrides merged into that graphic's data |
| `graphics` | extra graphics: `[{"component": "world-map", "at": "w:Reportedly", "data": {...}}]` |
| `impacts` | anchors for a 6-frame shake and a white flash |
| `sfx` | `[{"n": "boom", "at": "w:BOOM", "gain": 0, "repeat": 1}]`; without it, the shot's `sfx` names play at its start and its first impact |
| `grade` | `sepia`, `red`, `punch` |
| `backdrop` | the graphic background, default `grid` |
| `captions` | `false` to hide captions (end cards) |
| `year` | the year ticker for this shot |
| `presenter_in`, `presenter_entrance` | when and how the host enters: `left`, `right`, `pop` |
| `silhouette`, `notes` | kit effects used once in the example (TB2 silhouette, music notes) |

## Kit components

`animative/kit/kit.js` draws every graphic. Name one in a shot's `graphic.component`:

`kinetic-caption` · `name-card` · `title-card` · `year-ticker` · `stamp` · `spec-card` ·
`counter` · `end-card` · `map-arc` · `world-map` · `diagram` · `swarm` · `timeline`

`diagram` picks a drawing by `data.name`. The four drawn for the drone war (`fpv-payload`,
`bekaa-1982`, `loiter-dive`, `fpv-jam-vs-fibre`) show how one is built. A new topic usually needs
a new diagram. Add a `D["<name>"] = function (svg, d, t0, t1) { ... }` in `kit.js`, built from the
same helpers. Seek-safe only: every animation goes on the shot's GSAP timeline, positioned in
seconds, never `setTimeout` or CSS transitions.
