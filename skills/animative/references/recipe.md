# Recipe — an animative video from topic to final

How the drone-war video was actually built, as commands. Every path is under
`projects/<slug>/`. Timings are from that build (38 shots, 3:10, on a 6-vCPU Linux box), for planning.

| Step | Took | Note |
|---|---|---|
| Research and fact-check | about 10 min | 16 claims, each with a source |
| Sourcing, in parallel | about 70 min | DVIDS and Freesound are slow; start them first |
| Voice, 10 beats | about 2 min a pass | $0.10 a pass on Gemini 2.5 Pro TTS |
| Draft render, 38 shots, 3 at a time | 2.5 min | |
| Final render, 1080p, 2 at a time | 15 min | a rerun renders only changed shots |

## 0. Files

| File (in `episode/`) | Holds | Who writes it |
|---|---|---|
| `episode.json` | title, summary, character, voice style, glossary, shots | you, approved at gate 1 |
| `beats/*.md` | every spoken word, with `[direction]` tags | you, approved at gate 1 |
| `facts.json` | every claim: verdict, note, source URL | you, before the script is shown |
| `generated.json` | prompts for illustration stills and clips | you |
| `edit.json` | the cut: file and in-point per shot, word cues, impacts, effects, extra b-roll | you, while building the draft |
| `approvals/` | pinned voice takes, one file per beat | `animative pin`, after gate 2 |
| `credits.md` | every source, ready for the description | `animative credits` |

Start from the blank template or from the example:

```bash
animative new <slug>                    # blank: one beat, one shot
animative new <slug> --from drone-war   # the full worked example
```

## 1. Script and shot plan (gate 1)

- **Beats**: one file per section, front matter `beat`, `start`, `end` (planned whole seconds).
  Roughly 2.3 spoken words a second once shouts and pauses are in.
- **Direction tags** go at the start of a line or inline:

  | Tag | Means |
  |---|---|
  | `scream`, `shout` | full volume, raw; scream is higher and shorter |
  | `whisper`, `low`, `dark` | quiet and close; low and dark drop pitch and pace |
  | `fast`, `quick`, `breathless`, `rising` | pace up; rising builds into the next line |
  | `slow`, `big`, `heavy`, `awe` | weight and space; big is announcer scale |
  | `excited`, `storyteller` | energy without shouting; storyteller is warm |
  | `beat` | a deliberate pause of about half a second |

- **Shots** in `episode.json`: `id`, `beat`, `start`, `end`, `kind` (`archival`, `still_motion`,
  `graphic`), `what`, camera `size`/`angle`/`movement`, optional `graphic` (a kit component and
  its data), optional `presenter` (`pose`, `feeling`, `placement`), `sfx` names, and `source`
  (`want`, `url`, `license`, `credit`). Poses and feelings come from the character's `rig.json`;
  `animative sheet <host>` shows them all.
- **Glossary**: `pronunciations` for every name a voice will mangle.
- `voice_style`: one or two sentences on who the narrator is and how they sound.

`animative plan <slug>` renders all of it as one page. Show it, wait for approval.

## 2. Sources, effects, music (start these first, in parallel)

- Fetch every `source.url` into `assets/sources/`, named by shot (`s04-abrams.jpg`). Beside each,
  write `assets/sources/licenses/<stem>.txt`: page URL, license, author, fetch date.
- Public domain: US military media (DVIDS, af.mil, navy.mil), NASA, national archives. Creative
  Commons: Wikimedia Commons file pages (take the license from the page, not from a search
  result).
- **Trap: DVIDS timecodes are approximate.** A clip described as "takeoff at 0:58" was an
  interview face. Scan every video before choosing an in-point: one frame every 3 s into a
  contact sheet, then set `in` and `len` (usable seconds) in `edit.json`.
- **Trap: faces and name captions in sourced photos.** Crop them out with `precrop`, or move `in`.
- Effects (`sfx` provider `freesound-cc0`): Freesound with the CC0 filter (HQ previews need no
  login). Save to `assets/sound/sfx/`, a proof per file in `assets/sound/licenses/`, and list them
  in `assets/sound/index.json` (`name`, `file`, `author`, `source_url`, `license`).
- Music (`builtin`): `animative music <slug>` writes `assets/sound/music/bed.wav`, then in
  `edit.json`: `"music": {"file": "sound/music/bed.wav", "lufs": -20}`. Other providers:
  `animative import <slug> music bed <file> --via <provider> --license ... --page ...`.

## 3. Generated stills and clips (optional)

List them in `generated.json` (`stills` and `clips`: `id`, `for`, `prompt`; plus shared `rules`).

- `image: agy` → `animative stills <slug> [id ...]`. With `aswap` installed it rotates
  accounts on a quota error. The image quota is separate from chat quota, and a 429 looks like a
  hang.
- Any other provider: make the file however that provider works, then
  `animative import <slug> still <id> <file> --via <provider>`. Use `clip` for video.
- Then add them to `edit.json → sources` as `"gen:<id>": {"file": "generated/<via>/<id>.png"}`.

## 4. Voice

```bash
animative voice <slug> prompt cold-open    # what will be sent, spend nothing
animative voice <slug> estimate            # cost; ask first if over a dollar
animative voice <slug> record              # every beat, or name beats
animative takes <slug>                     # transcript against script, per take
```

- `voice: gemini-api` uses `GEMINI_API_KEY` from `.env` (several keys rotate when
  one runs out of quota). `voice: vertex` uses gcloud Application Default Credentials and
  `--vertex_project`. The drone-war voice was `gemini-2.5-pro-tts` on Vertex, voice `Fenrir`
  (Google calls it excitable): 22 takes, $0.22.
- Browser (AI Studio) or manual: get the per-beat prompt with `voice ... prompt`, make the take,
  then `animative import <slug> voice <beat> <file> --via ai-studio-web`.
- **Trap: stage notes get spoken.** "(pause)" was read aloud once. `[beat]` now compiles to an
  ellipsis. Always run `takes`. A word under "added" that is not a spelling variant means
  re-record that beat.
- Name the chosen take per beat in `edit.json → voice`, or leave it empty for the newest.

## 5. Draft

```bash
animative draft <slug>             # timing, compose, render, mix, assemble
animative draft <slug> compose     # or one step at a time
```

The draft lands in `videos/<slug>-draft.mp4`, 540p. Media not fetched yet is skipped with a note,
so a draft can be built while sourcing is still running. Rendering is local by default. Set
`render_docker: true` in `edit.json` (or `ANIMATIVE_DOCKER=1`) for pinned, identical renders.

Defaults that worked:

| Setting | Value | Why |
|---|---|---|
| Shot cut | 0.12 s before the cue word (`edit.json` `cue: "w:Word"`) | proportional retiming drifted by whole lines |
| Longest hold of one picture | **3.6 s**, then a new crop of it | 4.2 s with only a new move read as one still held 8 to 12 s |
| Voice | -16 LUFS | |
| Music bed | -20 LUFS, ducked **12 dB** under the voice, 80 ms attack, 300 ms release | |
| Effects | -20 LUFS each, then a **-7.5 dB** bus (`sfx_gain_db`) | -4 dB was "a bit loud" in review |
| Render concurrency | 3 shots at 540p, 2 at 1080p, 2 Chrome workers each (`ANIMATIVE_CONCURRENT`, `ANIMATIVE_WORKERS`) | 6 vCPU, 13 GB |

- **Trap: the render cache must key on the kit.** A shot's cache key is its page, the kit files
  and the first 64 KB of each media file. A kit change therefore re-renders every shot. Late in a
  final, fix in `edit.json` (one shot) rather than in `kit.js` or `kit.css`.
- **Trap: nothing may tween before time 0.** GSAP shifts the whole timeline to fit a child at a
  negative time, and every graphic then runs about 2 s late. The kit clamps it.
- **Trap: caption collision.** Scaling a shouted word grows it into its neighbours
  ("andIsraelijets"). Emphasis moves vertically only, and the room is reserved in the layout.
- **Trap: telemetry inside Docker.** `HYPERFRAMES_NO_TELEMETRY=1` on the host does not reach the
  render container. Build the image with `animative/kit/docker/Dockerfile.no-telemetry` on top
  of the HyperFrames render image if you use Docker.
- **Trap: npm 11 holds back install scripts.** `npm ci` warns that esbuild's postinstall was not
  run. Renders work without it; approve it with `npm approve-scripts esbuild` if one ever fails.

## 6. Watch it before anyone else does

Make contact sheets: one frame every 2 s, 12 per sheet (`ffmpeg -vf "fps=1/2,scale=480:-1,tile=4x3"`).
Read them all. Check list, from the drone-war review:

| Look for | Drone-war example | Fix in |
|---|---|---|
| A picture that does not match its words | a Predator photo in the 1982 beat | `edit.json` sources, or frame wider and add a name card |
| A figure on screen that the voice contradicts | the map read "8 COUNTRIES" against "more than thirty" | show the spoken figure from the first frame |
| Captions touching | "andIsraelijets" | the kit; never scale words horizontally |
| One picture held past 4 s | the TB2 and Wing Loong photos | more crops (`crops`), or cut away (`graphics` with `at`) |
| Washed-out footage | the XQ-58 launch clip | `grade: "punch"`, or another clip |
| Year ticker out of step | the FPV beat opened on 2019 | `year` on the shot |
| Text shown twice | the end-card question as card and caption | `captions: false` on the shot |
| Faces or logos in a sourced picture | officials under the Kızılelma | `precrop`, or move `in` |

## 7. Approve and final (gate 2)

```bash
animative pin <slug> --by "<who>" --via "<how they approved>"   # pins the draft's takes
animative pin <slug> --check
animative final <slug>                                          # 1080p, reads only pins
animative credits <slug>                                        # episode/credits.md
```

Start the final as soon as the fixes compose, and keep reviewing the draft while it renders. A
late fix then re-renders only the shots it touches. The final scales video sources to 1920 px
(the draft uses 1280 px), so the two never share a cached file.

## 8. Deliver

The person is waiting for one file, not for an archive. Send `videos/<slug>.mp4` (or its upload
link) first, then tidy everything else.
