# Draw.io Generation Notes

## Output Format

Use a single practical `.drawio` output unless the user asks for variants.

Keep the original `.drawio` in place. Write converted or repaired `.drawio` deliverables to the `out/` folder beside the source/requested output path. Put preview images and exported VSDX files in the same `out/` folder. Delete temporary files, unused repair passes, extracted models, comparison pages, and experimental variants after use.

For image inputs, rebuild the diagram as editable draw.io shapes and text. Use the image as a visual reference for layout, colors, hierarchy, and labels; do not produce a VSDX that is only a pasted bitmap unless the user explicitly asks for a raster-only result.

Preferred `<diagram>` payload for this workflow:

- raw-deflate compressed draw.io payload
- Base64 encoded
- not URL-escaped in the final `<diagram>` text
- ASCII only: `[A-Za-z0-9+/=]`

This avoids common browser importer errors:

- `Failed to execute 'atob' ... not correctly encoded`: Base64 was URL-escaped as `%2B`, `%2F`, `%3D`.
- `characters outside of the Latin1 range`: uncompressed XML with Chinese text was placed directly in `<diagram>` and importer called `atob()`.

## XML Skeleton

```xml
<mxfile host="app.diagrams.net" version="24.7.17">
  <diagram id="page-1" name="Page-1">BASE64_HERE</diagram>
</mxfile>
```

The decompressed payload must be:

```xml
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
  </root>
</mxGraphModel>
```

## Structural Checks

- IDs are unique.
- IDs `0` and `1` are roots only.
- Vertex cells have `vertex="1"`, `parent`, and `mxGeometry`.
- Edge cells have `edge="1"`, `parent`, `source`, `target`, and relative `mxGeometry`.
- Every `parent`, `source`, and `target` exists.
- Avoid relying on HTML-only tricks for essential content.

## VSDX-Compatible Source Rules

Use the same source rules for newly generated and repaired diagrams. New diagrams should be created directly in this structure; repaired diagrams should be migrated into this structure.

- Do not rely only on HTML `<b>` for headings that must stay bold in Visio; use `fontStyle=1` or independent text cells.
- If one visual unit contains overlay text, title text, descriptive text, multiple font weights, or multiple text colors, split those roles into independent `mxCell`s.
- If text must appear in white or another specific color on a colored background, split the background and text into separate `mxCell`s. The background cell should usually have `value=""`; the text cell should be text-only with explicit `fontColor` and `fontStyle`.
- Do not use white, hidden, or placeholder text inside the main label to reserve visual space.
- Keep stable Chinese fonts such as `Microsoft YaHei`.
- Avoid large rounded corners, shadows, and excessive spacing when the file may be exported to VSDX.
- Run `audit-drawio` after generation and fix the generated source directly if it fails.

Do not use `repair-drawio` as a routine step for newly generated diagrams. If a new file needs repair, the generation structure was wrong and should be corrected.

## HTML Input

If the user provides HTML:

1. Search for embedded `<mxfile>`.
2. Search for `<mxGraphModel>`.
3. Search for `data-mxgraph`.
4. Search script blocks for compressed diagram data.
5. Convert the extracted graph to a normal `.drawio`.

If no embedded draw.io graph exists and the HTML itself is the diagram source, rebuild the `.drawio` from DOM and CSS layout semantics:

- Map real containers such as figures, canvas/body areas, grids, side axes, cards, buses, and desc/footer panels. Do not infer body elements from header notes, captions, or legends.
- Compute geometry from CSS box-model values: padding, gaps, column counts, and intended boundaries. Aligned sibling regions must share the same `x + width`; never treat a target right boundary as usable width.
- For grid/flex-like track layouts such as `left fixed + gap + flexible center + gap + right fixed`, reserve fixed tracks and gaps before computing the center width. The center/body region must end before the right gap and fixed track; it must not cover side axes, legends, labels, or fixed panels.
- Generate only side axes that exist in the source DOM, and stop each axis at its related body/canvas content rather than footer or description panels.
- For vertical upright text (`writing-mode: vertical-rl` / `text-orientation: upright`), use explicit per-character line breaks or separate text cells. Do not rely on narrow text boxes or automatic Chinese wrapping.
- Mark vertical text, side-axis text, rotated text, connector labels, and intentionally offset labels as special text that must be excluded from generic VSDX `TextXForm` normalization.
- After conversion, audit diagram count, side-axis count, inferred elements, track boundaries, right boundaries, side-axis height, vertical text encoding, and desc/footer overflow before VSDX export.

Do not treat the whole HTML file as a `.drawio`. If the generated `.drawio` structure differs from the HTML structure, fix the `.drawio` source first; VSDX color and `TextXForm` repair are export-fidelity steps, not substitutes for correcting wrong HTML mapping.
