---
name: animative
description: Make a character-hosted explainer video - a 2D host cut from sprite sheets the user generates, sourced public-domain and Creative Commons footage, generated stills and clips, an energetic directed voice-over, music, sound effects and kinetic captions, all moving all the time. Use when asked for an animated explainer, a character-hosted video, a documentary-style short on any topic, to make a 2D host character for videos, or anything involving the animative command.
---

# Animative: character-hosted explainers

An animative video is a 16:9 explainer, 2 to 4 minutes long. Footage and stills move constantly
(pans, zooms, crops, cuts every 2 to 4 s). A 2D host appears in cutaways and lip-syncs to the
voice, and every name, date and number on screen is a rendered graphic. The voice-over is
directed: shouts, screams and whispers are written into the script as tags.

The recipe was first used for a 3:10 video about combat drones, bundled as the `drone-war`
example. Read `references/recipe.md` before building anything: it holds every command, the
defaults that worked and the traps. `references/edit-json.md` explains the edit file.
`references/characters.md` covers making a host.

## First run

Do these once per machine, or whenever a step reports something missing.

1. **The engine.** Run `animative --version`. If the command is missing, or older than this
   plugin's `.claude-plugin/plugin.json` version, install it from the plugin itself:
   `uv tool install --force "${CLAUDE_PLUGIN_ROOT}"`. Add `[edge]` or `[kokoro]` to the path in
   quotes for those voices, for example `"${CLAUDE_PLUGIN_ROOT}[edge]"`. Needs Python 3.12+ and
   uv; if uv is missing, say so and give the install link (https://docs.astral.sh/uv/).
2. **A workspace.** Ask where videos should live (default: a new `animative` folder in their
   home or projects directory), then run `animative init <dir>` and work from there. API keys go
   in that folder's `.env`.
3. **The render kit.** Run `animative setup`. It needs Node 22+ and npm. ffmpeg and ffprobe must
   be on PATH too; `animative doctor` lists everything.
4. **Tools.** See "Ask which tools to use" below.
5. **A host.** With no character in `characters/` yet, make one before the first video. Follow
   `references/characters.md` with them. It takes a base figure, two or three sprite sheets from
   their image tool, and a rig. This is the step people enjoy; take it slowly and show the model
   sheet.

## Ask which tools to use

Nobody has the same generators, so never assume one. Run `animative doctor`. For each
capability it lists as "not chosen yet" (`image`, `video`, `voice`, `music`, `sfx`):

- Ask one question, using the options from the doctor output.
- Mark the options found on this machine.
- Say plainly what an option cannot do: edge and Kokoro cannot shout, and Flow downloads can stall.

Save each answer with `animative providers set <capability> <option> [--key value]`, for example
`animative providers set voice gemini-api --voice Fenrir`. Choices are per person and live in the
user config folder. Keep the alternatives: ask again only when they want to switch, or when a
chosen tool stops working. Then offer the next option rather than failing.

| Mode | Who does it | How the file arrives |
|---|---|---|
| `cli` | `animative` calls the tool (agy stills, Gemini or Vertex voice) | written in place, with a sidecar |
| `agent` | you drive another CLI or API yourself (Codex, Lyria on Vertex, Freesound) | `animative import` |
| `browser` | you drive a logged-in tab with Playwriter (ChatGPT, Gemini, Flow, AI Studio) | download, then `animative import` |
| `manual` | you print the exact prompt and file name; they make the file and drop it in `projects/<slug>/assets/inbox/` | `animative import` |
| `builtin` | animative itself (music bed, edge voice) | written in place |

A browser login that has expired is theirs to fix: say which site, wait, then continue.

## The approval gates

They approve two things. Nothing is spent, and nothing renders at full quality, before each one.

1. **The script and the shot plan.** Research the topic and put every claim, with a source, in
   `facts.json`. Write the beats and the shot list, run `animative plan <slug>`, and show them the
   plan page (`projects/<slug>/build/plan.html`). Wait for approval or notes. Change the beats
   and shots, never the page.
2. **The draft.** Build the draft and watch it yourself first: contact sheets, and the check
   list in the recipe. Fix what you find, then hand it over. Once they approve, pin the takes
   the draft used (`animative pin <slug> --by <name> --via "<how they said it>"`) and build the
   final.

Before any paid generation (a Gemini or Vertex voice, Lyria), state the estimate
(`animative voice <slug> estimate`). Get a yes when it is over a dollar.

## House rules

- **No watermarks, stamps or "draft" labels on any frame, ever.** A draft is the final, smaller.
- **Anything a viewer reads is a graphic.** Never ask an image or video model for legible text.
- **Generated material is illustration, never evidence.** No generated clip may pose as real
  footage of a real event. No identifiable real people unless it is the user's own host, no
  logos, no casualties.
- **Sourced media is public domain or Creative Commons**, credited (`animative credits`), with
  a license proof beside every file. No state propaganda outlets, no press kits, nothing showing
  people being hurt.
- **Every claim has a source** in `facts.json`. Soften a line rather than ship an unsourced one.
- **No picture holds longer than about 3.6 s.** Cut to another crop, another source or a graphic.
- **A host made from a real person's photo** stays with them. Don't share it or put it in a
  public place without their consent.
