# animative

**Character-hosted explainer videos, made with Claude Code.**

You make a 2D host once, from sprite sheets you generate with any image tool. Then give Claude a
topic. It researches and fact-checks it, writes a script with shouts and whispers, and plans every
shot. Once you approve the plan, it builds the video. Footage keeps moving, the host lip-syncs the
voice-over, and every name, date and number on screen is a crisp rendered graphic.

<p align="center"><img src="docs/img/showcase.gif" alt="The opening of a video: a title card, then a public-domain photo of a drone with a name card and kinetic captions" width="640"></p>

```text
/plugin marketplace add hrmasss/animative
/plugin install animative@animative
```

Then ask: *"make me a 3 minute explainer about the history of the bicycle"*.

---

## What comes out

Real frames from a build. The source photo is public domain. Everything else is drawn by the
graphics kit at render time, so text is always sharp and spelled right.

| | | |
|:-:|:-:|:-:|
| <img src="docs/img/showcase-s1.png" width="300" alt="Title card"> | <img src="docs/img/showcase-s2.png" width="300" alt="Photo with a name card"> | <img src="docs/img/showcase-s3.png" width="300" alt="World map with highlighted countries"> |
| **Title cards** | **Name cards** on sourced footage | **Maps** that light up the countries the voice names |
| <img src="docs/img/showcase-s4.png" width="300" alt="Animated diagram"> | <img src="docs/img/showcase-s5.png" width="300" alt="Big number counter"> | <img src="docs/img/showcase-s6.png" width="300" alt="Timeline"> |
| **Diagrams**, animated step by step | **Counters** for the numbers that matter | **Timelines** to recap |

Kinetic captions run under everything, timed to the word. A year ticker in the corner keeps the
story's date.

## How a video gets made

You approve twice. Nothing is spent on generation, and nothing renders at full quality, before
each approval.

```mermaid
flowchart TB
    topic([Your topic]) --> research["Research and fact-check<br/><i>every claim gets a source</i>"]
    research --> plan["Script by section, with direction tags<br/>+ a shot plan: camera, graphics, host, sound"]
    plan --> gate1{{"You approve the script and plan"}}
    gate1 --> footage["Footage and photos<br/><i>public domain and Creative Commons, with license proofs</i>"]
    gate1 --> gen["Generated stills and clips<br/><i>illustration only</i>"]
    gate1 --> voice["Directed voice-over<br/><i>shouts, whispers, pauses</i>"]
    gate1 --> sound["Music bed and sound effects"]
    footage & gen & voice & sound --> draft["Draft, 540p<br/><i>timed to the real voice</i>"]
    draft --> review["Claude watches it first:<br/>contact sheets, a check list"]
    review --> gate2{{"You approve the draft"}}
    gate2 --> final["Final, 1080p<br/>+ credits for the description"]
```

The script is written as *beats* (sections) with delivery tags the voice actually follows:

```markdown
[rising] Then came the hunters.
The MQ-1 Predator. American, built by General Atomics, first flown in 1994.
[shout] Hellfire! The first armed drone strikes, over Afghanistan.
And many of its crews? [beat] Sitting in a trailer in Nevada, half a world away.
```

## Your host

Any character works: you, a friend (with their OK), a mascot, an animal. You generate two kinds of
image with your usual tool, and the rest is mechanical.

```mermaid
flowchart LR
    ref["Base figure<br/><i>from a photo or a description</i>"] --> sheets["Sprite sheets<br/><i>poses with blank faces,<br/>rows of eyes, noses, mouths</i>"]
    sheets --> inspect["animative inspect<br/><i>numbers every piece</i>"]
    inspect --> rigj["rig.json<br/><i>labels, feelings,<br/>mouth shapes for speech</i>"]
    rigj --> cut["animative cut<br/><i>trims every part,<br/>finds every face</i>"]
    cut --> sheet["Model sheet<br/><i>every pose × every feeling,<br/>live lip-sync</i>"]
```

Faces are drawn blank on purpose. One set of eyes, noses and mouths then works on every pose, and
the cut finds each pose's face by itself:

<p align="center"><img src="docs/img/face-placement.svg" alt="A blank-faced pose, the detected face box and beard line, and the placed eyes, nose and mouth" width="760"></p>

A feeling is a recipe in the rig: which pose, which eyes (tilted a few degrees for sad or angry
brows), which mouth. Twelve feelings and ten mouth shapes cover a whole video. Single-frame poses
move with squash and stretch, so no in-between drawings are needed.

## Techniques

### Lip-sync from the real voice

<p align="center"><img src="docs/img/lipsync.svg" alt="Words split into sound groups, each shown as a mouth shape" width="760"></p>

The voice-over is transcribed with word timings, and the script is aligned to them. Each word
becomes the classic animation sound groups (MBP, AI, E, O, U, FV, L…). A shouted word swaps in the
wide shout mouth. Shots cut 0.12 s before a cue word, so a picture changes exactly when the voice
says what it shows.

### Nothing sits still

<p align="center"><img src="docs/img/hold.svg" alt="One photo held for 9 seconds becomes three parts with different crops and camera moves" width="760"></p>

Every still gets a camera move (zoom, pan, truck, a slight dutch tilt). No picture holds longer
than 3.6 s: a longer hold becomes several framings of the same source. The 3.6 s figure came
out of review.

### The mix

<p align="center"><img src="docs/img/ducking.svg" alt="Voice, a music bed ducking 12 dB under it, and sound effects" width="760"></p>

Voice, music and effects are levelled to fixed loudness targets, then mixed sample by sample. The
music ducks under speech with a fast attack and a slow release, so it swells back between lines
instead of pumping.

### Honest by construction

- **Every claim has a source** in `facts.json`, checked before the script is shown to you.
- **Sourced media is public domain or Creative Commons**, with a license proof saved beside
  every file. `animative credits` writes the description credits.
- **Generated images are illustration, never evidence.** They never pose as footage of a real
  event, and never contain text.
- **No watermarks**, ever, not even on drafts.

## How it renders

```mermaid
flowchart LR
    spec["Shot spec<br/><i>episode.json + edit.json<br/>+ word timings</i>"] --> page["One HTML page per shot<br/><i>graphics kit + GSAP timeline</i>"]
    page --> hf["HyperFrames<br/><i>frame-exact headless render</i>"]
    hf --> clips["Shot clips<br/><i>cached by content hash</i>"]
    clips --> cat["ffmpeg<br/>assemble"]
    mix["Sound mix<br/><i>numpy: level, duck, place</i>"] --> cat
    cat --> out(["video.mp4"])
```

Every shot renders independently and is cached on the page, the kit and its media, so a fix
re-renders only the shots it touches. Timing is kept as rational frame numbers end to end; no
decimal frame rate ever appears. A 3-minute draft takes a few minutes on a 6-core CPU.

## Tools it can use

On first use Claude asks which of these you have, and remembers. It never assumes one.

| For | Options |
|---|---|
| Images | agy CLI, Codex CLI, ChatGPT or Gemini in your browser, or by hand |
| Video clips | Google Flow in your browser, by hand, or none (stills with camera moves) |
| Voice | Gemini TTS with an API key, Gemini TTS on Vertex AI, Google AI Studio in your browser, Kokoro, edge-tts, or by hand |
| Music | a bed generated offline, AI Studio, Lyria on Vertex, or a library track |
| Sound effects | CC0 effects from Freesound, or your own |

Browser options drive a tab you are already logged into, through Playwriter. By hand means Claude
writes the exact prompt and file name, and you drop the result in the project's inbox.

## Install

As a Claude Code plugin:

```text
/plugin marketplace add hrmasss/animative
/plugin install animative@animative
```

On first use, Claude installs the `animative` command with [uv](https://docs.astral.sh/uv/). It
then sets up a workspace, asks about your tools, and helps you make your host. You need Python
3.12+, uv, Node 22+ and ffmpeg. Docker is optional, for pinned, identical renders.

The engine also works on its own:

```bash
uv tool install git+https://github.com/hrmasss/animative
animative init && animative setup && animative doctor
```

It ships with *The Drone War* as a worked example: a 3:10 explainer with its script, a 38-shot
plan, a 16-claim fact-check and cleared sources (`animative new drones --from drone-war`). The
frames above are rebuilt by `docs/showcase/build.sh`.

## License

MIT. The bundled fonts (Anton, Inter) are under the SIL Open Font License 1.1.
