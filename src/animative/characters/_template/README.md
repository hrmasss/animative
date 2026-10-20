# <name>

A host character for animative videos. The full guide is
`.claude/skills/animative/references/characters.md`; this is the checklist.

1. **Base figure** → `reference.png`. One full-body figure, front view, plain white background.
2. **Sprite sheets** → `sources/*.png`. Transparent background, faces left blank, the last row
   for eyes, noses and mouths. Same scale and camera angle on every sheet.
3. **Rig** → `rig.json`. Run `animative inspect <name>`, read the numbered pictures, then
   write one group per block of pieces, with labels in reading order.
4. **Cut and check** → `animative cut <name>`, then `animative sheet <name>` and
   open the model sheet. Tune `face` with the face guides until every pose looks right.
5. **Ship it ready to use** → `animative cut <name> --bundle`, and commit `parts/`.
   A video uses it with `"character": "<name>"` in `episode.json`.
