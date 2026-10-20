#!/usr/bin/env bash
# Rebuild the README's frames from docs/showcase/episode. Needs the animative command,
# Node 22+ and ffmpeg (the same as any build). Writes docs/img/showcase-*.png and
# docs/img/showcase.gif; nothing else in the repo changes.
#
#   bash docs/showcase/build.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
img="$here/../img"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

animative init "$work/ws" >/dev/null
cd "$work/ws"
animative setup >/dev/null
mkdir -p projects/showcase
cp -r "$here/episode" projects/showcase/episode
mkdir -p projects/showcase/assets/sources projects/showcase/assets/sound
echo '[]' > projects/showcase/assets/sound/index.json
# public domain, U.S. Air Force
curl -fsSL -A "animative-showcase" -o projects/showcase/assets/sources/s2-predator.jpg \
  "https://commons.wikimedia.org/wiki/Special:FilePath/MQ-1_Predator,_armed_with_AGM-114_Hellfire_missiles.jpg?width=1920"
animative music showcase
animative draft showcase

video=projects/showcase/videos/showcase-draft.mp4
mkdir -p "$img"
# one frame per shot, 75% of the way in: every graphic has finished animating by then
python3 - "$video" "$img" projects/showcase/build/draft/timing.json <<'PY'
import json, subprocess, sys
video, out, timing = sys.argv[1:]
t = json.load(open(timing))
num, den = t["fps"]
for s in t["shots"]:
    at = (s["f0"] + 0.75 * (s["f1"] - s["f0"])) * den / num
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", video, "-frames:v", "1",
                    "-vf", "scale=960:-2", f"{out}/showcase-{s['id']}.png"], check=True)
PY
# the first two shots as a loop: title card, then the photo with its name card and caption
ffmpeg -v error -y -t 9 -i "$video" -vf "fps=12,scale=640:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" "$img/showcase.gif"
ls -la "$img"
