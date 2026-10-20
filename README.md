# animative

Character-hosted explainer videos, made with Claude Code.

You make a 2D host once, from sprite sheets you generate with any image tool. Then you give
Claude a topic. It researches and fact-checks it, writes a script with shouts, whispers and
pauses, and plans every shot. Once you approve the plan, it builds the video:

- public-domain and Creative Commons footage, credited, with license proofs
- generated stills and clips, from whichever tool you have
- a directed voice-over, with your host lip-syncing it
- music, sound effects, maps, name cards, diagrams and kinetic captions
- nothing ever sitting still: cuts every 2 to 4 seconds, constant camera moves

You approve twice: the script and shot plan, then the draft. Nothing is stamped or watermarked,
not even drafts.

It ships with *The Drone War* as a worked example: a 3:10 explainer on combat drones, with its
script, 38-shot plan, fact-check and cleared sources.

## Install

As a Claude Code plugin:

```text
/plugin marketplace add hrmasss/animative
/plugin install animative@animative
```

Then ask Claude for a video. On first use it installs the `animative` command (with
[uv](https://docs.astral.sh/uv/)), sets up a workspace, and asks which tools you have for
images, video, voice, music and sound effects. It never assumes one.

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+ and ffmpeg. Docker is optional.

The engine also works on its own:

```bash
uv tool install git+https://github.com/hrmasss/animative
animative init && animative setup && animative doctor
```

## Tools it can use

| For | Options |
|---|---|
| Images | agy CLI, Codex CLI, ChatGPT or Gemini in your browser, or by hand |
| Video clips | Google Flow in your browser, by hand, or none (stills with camera moves) |
| Voice | Gemini TTS with an API key, Gemini TTS on Vertex AI, Google AI Studio in your browser, Kokoro, edge-tts, or by hand |
| Music | a bed generated offline, AI Studio, Lyria on Vertex, or a library track |
| Sound effects | CC0 effects from Freesound, or your own |

Browser options drive a tab you are already logged into, through Playwriter. By hand means
Claude writes the exact prompt and file name, and you drop the result in the project's inbox.
Your choices are saved per person and stay changeable.

## Your host

Any character works: you, a friend, a mascot, an animal. Claude walks you through it:

1. Generate a base figure from a photo or a description.
2. Generate sprite sheets: poses with blank faces, plus rows of eyes, noses and mouths.
3. `animative inspect` numbers every piece on each sheet, so Claude can write the rig: labels,
   feelings, and mouth shapes for speech.
4. `animative cut`, then `animative sheet` opens a model sheet that shows every pose with every
   feeling, and a live lip-sync.

The prompts that made the first host are in the skill
(`skills/animative/references/characters.md`).

## How it renders

Every shot is an HTML page animated with GSAP and rendered frame-exact by
[HyperFrames](https://github.com/heygen-com/hyperframes). The sound is mixed with numpy, and
everything is assembled with ffmpeg. A 3-minute draft renders in a few minutes on a laptop-class
CPU.

## License

MIT. The bundled fonts (Anton, Inter) are under the SIL Open Font License 1.1.
