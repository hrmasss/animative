"""Cut a character's generated sheets into labelled parts and find each pose's face.

A character is two authored things: the generated sheets under
``characters/<name>/sources/`` and a hand-written ``rig.json`` naming every
piece on them. Everything else is derived and lands in the workspace cache
(or ``characters/<name>/parts/`` with ``--bundle``): one trimmed PNG per pose, eye, nose,
mouth and beard, plus ``rig.lock.json`` holding each pose's face box so the
renderer can place eyes, nose and mouth on it.

Why labels are matched by reading order and not by coordinates: a regenerated
sheet never puts a piece on the same pixel twice. ``rig.json`` gives each group a
box, a row count and its labels in reading order; the cut finds the pieces, sorts
them into rows, and refuses to write anything if the count is off, because a
silently shifted label puts a frown where a smile was meant.

The faces are drawn blank. The face box is the highest large skin-coloured region
of the pose; the beard line is where that skin ends below its centre. Eyes, nose
and mouth are positioned from those two numbers, so they follow each pose without
per-pose tuning. ``face_overrides`` in ``rig.json`` corrects one if it is wrong,
and ``faceless`` lists poses turned away from camera.

    animative cut <name>
    animative sheet <name>     # the model sheet beside the parts
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from animative import config, layout

# Generated "transparent" PNGs carry 1-2 alpha haze over the whole canvas and top
# out at 254. Below NOISE is haze, above SOLID is meant to be opaque.
NOISE, SOLID, MASK = 12, 245, 64
PAD = 2


def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """ndi.label, typed: its stubs allow a bare count, but with no output array it returns both."""
    return cast(tuple[np.ndarray, int], ndi.label(mask))


def clean_alpha(rgba: np.ndarray) -> np.ndarray:
    a = rgba[..., 3]
    a[a < NOISE] = 0
    a[a >= SOLID] = 255
    return rgba


def erase_grid_lines(rgba: np.ndarray) -> np.ndarray:
    """Drop the thin cell borders some sheets are drawn with.

    A border is a row or column with alpha along most of its length. (Not less: a row
    through a strip of mouths can be half solid, and its thin line-mouths would go.)
    Only the pixels with background on both
    sides are cleared, so a pose crossing the line keeps its pixels. Past the sheet's
    edge counts as background, so the outer frame goes too.
    """
    a = rgba[..., 3]
    h, w = a.shape
    solid = a >= MASK
    rows = np.where(solid.sum(1) > w * 0.55)[0]
    cols = np.where(solid.sum(0) > h * 0.55)[0]
    clear = np.zeros(w, dtype=bool)
    for y in rows:
        above = a[y - 3] < MASK if y - 3 >= 0 else ~clear
        below = a[y + 3] < MASK if y + 3 < h else ~clear
        a[y, above & below] = 0
    clear_h = np.zeros(h, dtype=bool)
    for x in cols:
        left = a[:, x - 3] < MASK if x - 3 >= 0 else ~clear_h
        right = a[:, x + 3] < MASK if x + 3 < w else ~clear_h
        a[left & right, x] = 0
    return rgba


def find_pieces(alpha: np.ndarray, min_area: int, merge_gap: int):
    """Pieces inside one group box: their boxes [x0, y0, x1, y1] and label ids.

    The ids matter because a piece's box can take in a neighbour's edge or a
    number badge; only pixels under the piece's own labels are kept.
    """
    solid = alpha >= MASK
    labels, _ = _label(ndi.binary_dilation(solid, iterations=3))
    pieces = []
    for k, sl in enumerate(ndi.find_objects(labels), start=1):
        if sl is None:
            continue
        if int((solid[sl] & (labels[sl] == k)).sum()) < min_area:
            continue
        pieces.append(([sl[1].start, sl[0].start, sl[1].stop, sl[0].stop], [k]))
    if merge_gap:
        pieces = merge_stacked(pieces, merge_gap)
    return pieces, labels


def merge_stacked(pieces: list, gap: int) -> list:
    """Join pieces drawn as one part but not touching, like a brow over its eye."""
    merged = True
    while merged:
        merged = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                (a, ia), (b, ib) = pieces[i], pieces[j]
                overlap = min(a[2], b[2]) - max(a[0], b[0])
                narrow = min(a[2] - a[0], b[2] - b[0])
                vgap = max(a[1], b[1]) - min(a[3], b[3])
                if overlap > narrow * 0.5 and vgap <= gap:
                    box = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    pieces[i] = (box, ia + ib)
                    del pieces[j]
                    merged = True
                    break
            if merged:
                break
    return pieces


def reading_order(pieces: list, rows: int) -> list:
    """Split into `rows` bands at the widest vertical gaps, then left to right."""
    def mid(p):
        return (p[0][1] + p[0][3]) / 2

    by_y = sorted(pieces, key=mid)
    gaps = sorted(range(1, len(by_y)), key=lambda i: mid(by_y[i]) - mid(by_y[i - 1]), reverse=True)
    bands, start = [], 0
    for c in [*sorted(gaps[: rows - 1]), len(by_y)]:
        bands.append(sorted(by_y[start:c], key=lambda p: p[0][0]))
        start = c
    return [p for band in bands for p in band]


#: A warm light-to-medium skin tone, the default. A character sets its own range in
#: rig.json -> face_detect.skin (sample the face's colour from reference.png).
SKIN = {"r_min": 190, "g_min": 120, "g_max": 210, "b_min": 70, "b_max": 170, "r_minus_b": 60}


def skin_mask(rgb: np.ndarray, skin: dict | None = None) -> np.ndarray:
    k = {**SKIN, **(skin or {})}
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    return ((r > k["r_min"]) & (g > k["g_min"]) & (g < k["g_max"]) & (b > k["b_min"]) & (b < k["b_max"])
            & (r - b > k["r_minus_b"]))


def find_face(rgba: np.ndarray, skin_cfg: dict | None = None) -> dict:
    """Face box and beard line of a blank-faced pose, in cutout pixels.

    The "beard line" is where the face's skin ends below its centre: the top of the
    beard on a bearded host, the chin on a clean-shaven one. Mouth placement is
    measured from it (rig.json face.mouth_y), so a beardless host uses a negative
    mouth_y to sit the mouth above the chin.
    """
    skin = skin_mask(rgba[..., :3], skin_cfg) & (rgba[..., 3] >= SOLID)
    skin = ndi.binary_opening(skin, iterations=1)
    labels, n = _label(skin)
    if not n:
        raise SystemExit("no face found")
    # The face is the highest large skin region. Arms can be bigger and a dive can drop
    # the head low, but nothing big sits above the face; a raised fist is too small.
    idx = range(1, n + 1)
    areas = np.array(ndi.sum(skin, labels, idx))
    tops = np.array([sl[0].start for sl in ndi.find_objects(labels)])
    big = np.where(areas >= areas.max() * 0.4)[0]
    k = int(big[np.argmin(tops[big])]) + 1
    ys, xs = np.where(labels == k)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    cx = (x0 + x1) // 2
    centre = np.where((labels[:, cx - 2:cx + 3] == k).any(1))[0]
    beard = int(centre.max()) + 1 if len(centre) else y1
    return {"box": [x0, y0, x1, y1], "beard_y": beard}


def cut(entity: str, bundle: bool = False) -> dict:
    """Cut every sheet of a character; return the lock (also written to rig.lock.json).

    ``bundle`` writes into ``characters/<name>/parts/`` so the parts can be committed
    and used from a fresh clone; otherwise the cut goes to the workspace cache.
    """
    src = layout.character_dir(entity)
    rig = json.loads((src / "rig.json").read_text(encoding="utf-8"))
    out = layout.bundled_cut_dir(entity) if bundle else config.cache_dir() / "characters" / entity
    # Start clean: a renamed label must not leave its old file behind.
    shutil.rmtree(out, ignore_errors=True)
    sheets = {}
    for name, rel in rig["sources"].items():
        rgba = np.array(Image.open(src / rel).convert("RGBA"))
        sheets[name] = erase_grid_lines(clean_alpha(rgba))

    lock = {"id": rig["id"], "cut_at": date.today().isoformat(),
            "inputs_hash": layout.character_inputs_hash(entity), "parts": {}}
    detect = rig.get("face_detect", {})
    manual = detect.get("mode") == "manual"
    overrides = rig.get("face_overrides", {})
    seen: set[str] = set()
    for g in rig["groups"]:
        sheet = sheets[g["source"]]
        gx0, gy0, gx1, gy1 = g["box"]
        region = sheet[gy0:gy1, gx0:gx1]
        pieces, labels = find_pieces(region[..., 3], g.get("min_area", 50), g.get("merge_gap", 0))
        if len(pieces) != len(g["items"]):
            raise SystemExit(
                f"{g['source']} {g['kind']} box {g['box']}: found {len(pieces)} pieces, "
                f"rig.json names {len(g['items'])}. Fix the box or the labels."
            )
        for label, ((x0, y0, x1, y1), ids) in zip(g["items"], reading_order(pieces, g["rows"]), strict=True):
            if label in seen:
                raise SystemExit(f"duplicate label {label}")
            seen.add(label)
            x0, y0 = max(x0 - PAD, 0), max(y0 - PAD, 0)
            x1, y1 = min(x1 + PAD, region.shape[1]), min(y1 + PAD, region.shape[0])
            piece = region[y0:y1, x0:x1].copy()
            piece[..., 3][~np.isin(labels[y0:y1, x0:x1], ids)] = 0
            path = out / f"{g['kind']}s" / f"{label}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(piece).save(path, optimize=True)
            entry = {
                "kind": g["kind"],
                "file": path.relative_to(out).as_posix(),
                "size": [x1 - x0, y1 - y0],
                "source": g["source"],
                "at": [gx0 + x0, gy0 + y0],
            }
            if g["kind"] == "pose":
                # A pose turned away from camera has no face to fill.
                faceless = label in rig.get("faceless", [])
                if faceless:
                    entry["face"] = None
                elif label in overrides:
                    entry["face"] = overrides[label]
                elif manual:
                    raise SystemExit(f"face_detect is manual: add face_overrides.{label} = "
                                     '{"box": [x0, y0, x1, y1], "beard_y": y} (pose pixels)')
                else:
                    entry["face"] = find_face(piece, detect.get("skin"))
            lock["parts"][label] = entry

    (out / "rig.lock.json").write_text(json.dumps(lock, indent=1) + "\n", encoding="utf-8")
    counts = {}
    for p in lock["parts"].values():
        counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    print(f"{entity}: " + ", ".join(f"{n} {k}s" for k, n in counts.items()) + f" -> {out}")
    return lock


ensure_cut = layout.ensure_cut


def inspect(entity: str, min_area: int = 60) -> list[Path]:
    """Number every piece on every sheet of a character, to write rig.json groups from.

    For each sheet: a picture with a numbered box round each piece found, and a JSON
    list of those boxes. Read the picture, then give each block of pieces a group
    whose box encloses them, with labels in reading order.
    """
    from PIL import ImageDraw

    src = layout.character_dir(entity)
    rigj = json.loads((src / "rig.json").read_text(encoding="utf-8"))
    out = config.cache_dir() / "characters" / entity / "inspect"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for key, rel in rigj["sources"].items():
        rgba = erase_grid_lines(clean_alpha(np.array(Image.open(src / rel).convert("RGBA"))))
        # no merging here: a brow shown apart from its eye says that group needs merge_gap: 2
        pieces, _ = find_pieces(rgba[..., 3], min_area, 0)
        ordered = sorted(pieces, key=lambda p: (round((p[0][1] + p[0][3]) / 2 / 40), p[0][0]))
        a = rgba[..., 3:4].astype(float) / 255
        flat = (rgba[..., :3] * a + 255 * (1 - a)).astype("uint8")
        img = Image.fromarray(flat)
        d = ImageDraw.Draw(img)
        boxes = []
        for i, (box, _ids) in enumerate(ordered):
            d.rectangle(box, outline=(230, 40, 40), width=2)
            d.text((box[0] + 3, box[1] + 2), str(i), fill=(230, 40, 40))
            boxes.append({"n": i, "box": [int(v) for v in box], "w": int(box[2] - box[0]), "h": int(box[3] - box[1])})
        png = out / f"{key}.png"
        img.save(png)
        (out / f"{key}.json").write_text(json.dumps(boxes, indent=1), encoding="utf-8")
        print(f"{key}: {len(boxes)} pieces -> {png}")
        written.append(png)
    return written


def sheet(entity: str) -> Path:
    """Write the proof page: the rig composed live, beside the parts it loads."""
    rig = json.loads((layout.character_dir(entity) / "rig.json").read_text(encoding="utf-8"))
    out = ensure_cut(entity)
    lock = json.loads((out / "rig.lock.json").read_text(encoding="utf-8"))
    parts = lock["parts"]
    missing = []
    for name, e in rig["expressions"].items():
        if name == "_":
            continue
        for ref in [e["pose"], e["mouth"], *e["eyes"], *([e["nose"]] if "nose" in e else [])]:
            if ref != "mirror" and ref not in parts:
                missing.append(f"expression {name}: {ref}")
    for code, v in rig["visemes"].items():
        if code != "_" and v["mouth"] not in parts:
            missing.append(f"viseme {code}: {v['mouth']}")
    for key in ("eye_ref", "mouth_ref", "nose"):
        if rig["face"][key] not in parts:
            missing.append(f"face.{key}: {rig['face'][key]}")
    if missing:
        raise SystemExit("rig.json names parts the cut did not produce:\n  " + "\n  ".join(missing))
    data = {
        "id": rig["id"],
        "sheets": len(rig["sources"]),
        "parts": parts,
        "cut_at": lock["cut_at"],
        "face": rig["face"],
        "expressions": rig["expressions"],
        "visemes": rig["visemes"],
        "limits": [x for x in rig.get("limits", []) if x.get("limit")],
    }
    template = Path(__file__).with_name("sheet.html").read_text(encoding="utf-8")
    page = template.replace("/*RIG*/null", json.dumps(data, separators=(",", ":")))
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{entity}: proof sheet -> {out / 'index.html'}")
    return out / "index.html"

