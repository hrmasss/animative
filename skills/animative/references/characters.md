# Characters

A character (a host) is a folder under `characters/<name>/` in the workspace. It holds the
generated sheets in `sources/`, a `reference.png` of the base figure, and a hand-written
`rig.json`. `animative cut <name>` turns it into parts. `animative sheet <name>` writes a model
sheet that composes every pose with every feeling live, lip-syncs a typed line, and lists what
the rig cannot do yet. Open it after every change.

## What a good host has

The first host, made for the drone-war video, ended up with:

- **36 poses:** 12 talking gestures, 12 actions, 12 themed.
- **Parts:** 12 eye pieces, 14 noses and 44 mouths.
- **On the rig:** 12 named feelings and 10 mouth shapes for speech.

That is plenty. One sheet of 12 talking poses with a row of eyes and mouths is enough to start;
add sheets as videos need them. Single-frame poses are animated with squash and stretch, so no
in-between frames are needed. A walk cycle and side views would each need their own sheet.

## Making a host

Two steps with any image model that can make images from a reference (ChatGPT, Gemini, agy, or
whatever was chosen for `image`). These are the prompts that made the first host, from a
photo of a person:

**1. The base figure**, from a photo of the person (with their consent) or a description:

> create a 2d chibi figure with plain white bg of this (photo attached)

**2. The sprite sheets**, with the base figure attached:

> create a 4x4 character grid / sprite sheet for this character to make animated explainer video,
> multiple poses, same perspective, keep the face without eyes and mouth and dedicate the last row
> grid for various eye and mouth combos to animate talking, emotion and so on. just use zoom and
> pan to make it dynamic, transparent background. pair mustache with lips to avoid complication,
> only beard stays at face. and maintain same perspective / camera angle for all pieces.

Repeat step 2 for more poses (gestures, actions, a themed set like combat). Ask for noses and for
more mouths in a parts row when a sheet comes back without them. Keep every sheet at the same
scale and camera angle, or parts will not line up.

Other people and other styles work the same way: a cartoon, a flat vector mascot, an animal, a
robot. Adapt the prompt to the character. For example, drop the moustache line for a clean-shaven
host, and ask for "eyes and mouth as separate pieces" for a style with no nose. What matters to
the rig is the same for any style:

- faces blank on every pose, and parts drawn at the same scale as the faces
- one camera angle throughout
- a transparent background
- the parts in rows, away from the poses

**3. Scaffold and inspect.**

```bash
animative character new rumi      # characters/rumi/: rig.json, README.md, sources/
# put the base figure at reference.png and the sheets in sources/, list them in rig.json "sources"
animative inspect rumi            # .animative/cache/characters/rumi/inspect/<sheet>.png
```

`inspect` draws a numbered box round every piece it finds on each sheet, and saves the boxes as
JSON beside the picture. Read the pictures, then write one group per block of pieces.

**4. The rig** (`rig.json`; the template has every field):

- `groups`: one per block of pieces. Each has `kind` (`pose`, `eye`, `nose`, `mouth`, `beard`),
  `source`, `box` (`[x0, y0, x1, y1]` pixels on that sheet, enclosing the block), `rows`, `items`
  (labels in reading order) and optional `min_area` and `merge_gap`. Use `merge_gap: 2` where
  inspect shows a brow apart from its eye. The cut refuses to write anything if it finds a
  different count than you named. When it does, fix the box (keep it off the sheet's edge
  lines) or the labels, never the count check.
- `faceless`: poses turned away from camera.
- `face_detect`: how each pose's blank face is found. By default it is the highest large region
  of a warm light-to-medium skin colour. For another skin tone or a non-human face, set `skin` to that
  colour range. With `mode: "manual"`, nothing is detected and every pose gets a
  `face_overrides` entry (`{"<pose>": {"box": [...], "beard_y": n}}`, in that pose's pixels).
- `face`: where eyes, nose and mouth sit, as shares of the face width. The "beard line" is where
  the face's skin ends below its centre: the top of the beard on a bearded host, the chin on a
  clean-shaven host. So a beardless host uses a negative `mouth_y`, around `-0.25`, to sit the
  mouth above the chin. Also set `blink` (the closed-eye piece) and `shout_mouth`.
- `expressions`: named feelings (`pose`, `eyes` as `[left, right]` or `[piece, "mirror"]`,
  `mouth`, `tilt` in degrees for sad or angry brows, `lift`). `neutral` is required.
- `visemes`: the mouth for each sound group (`rest`, `MBP`, `AI`, `E`, `O`, `U`, `FV`, `L`, `etc`,
  `open`). All ten are needed for lip-sync.

**5. Cut, check, ship.**

```bash
animative cut rumi                # parts into the cache
animative sheet rumi              # the model sheet: tune `face` with "Show face guides"
animative cut rumi --bundle       # parts into characters/rumi/parts/
```

Keep `parts/` with the rig and sheets (commit them if the workspace is a git repo). The host is
then ready to use from a fresh copy, with no cutting.
Each bundle records a fingerprint of the rig and sheets it was cut from. Edit either
and the bundle is set aside automatically and the cache is used instead, until you re-bundle.
Episodes choose a host with `"character": "rumi"` in `episode.json`.
