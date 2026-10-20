# Example · The Drone War

The first animative video: a 3:10 explainer on combat and warfare drones (who built each one,
when, and what it is for). Everything authored is here, exactly as it shipped. Media is not:
sources, voice takes, stills and renders are derived, and a fresh copy fetches and records its
own.

```bash
animative new drones --from drone-war --character <your host>
animative plan drones          # the script and shot plan as one page
animative draft drones         # builds with whatever media is in assets/ so far
```

| File | Holds |
|---|---|
| `beats/*.md` | every spoken word, with direction tags |
| `episode.json` | 38 shots: kind, camera, graphics, host cues, effects, source URL, license, credit |
| `edit.json` | the cut as built: files, in-points, word cues, impacts, effects, extra b-roll |
| `facts.json` | 16 claims, each checked, with a source |
| `generated.json` | prompts for the 10 illustration stills |
| `credits.md` | the description credits as written for the original cut |

The host cues name the poses of the host it was made with. Your host plays them with its own
poses: a pose it does not have becomes the pose for that shot's feeling. The file names in
`edit.json` (`sources/s04-...jpg`) are where a fresh build expects each file under `assets/`.
The URL and license for each are on its shot in `episode.json`.
