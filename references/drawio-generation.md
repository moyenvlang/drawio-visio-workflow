# Draw.io Generation Notes

## Output Format

Use a single practical `.drawio` output unless the user asks for variants.

Keep the original `.drawio` in place. Write converted or repaired `.drawio` deliverables to the `out/` folder beside the source/requested output path. Put `.drawio` preview images in the same `out/` folder. Delete temporary files, unused repair passes, extracted models, comparison pages, and experimental variants after use.

For VSDX export paths, final `.vsdx` placement, package validation, color normalization, `TextXForm`, Visio COM previews, and Stage 2 comparison belong to `references/vsdx-export.md`.

Before conversion or export, generate a worklist in `out/` that maps each source page/container to its draw.io page and expected preview artifacts. For multi-page inputs, every later preview, comparison, and Visio validation step must follow this mapping.

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
- Prefer `rounded=0` for VSDX-targeted rectangles because draw.io fixed-radius corners can render much larger in Visio Desktop than in draw.io previews. Avoid rounded corners, shadows, and excessive spacing when the file may be exported to VSDX.
- Run `audit-drawio` after generation and fix the generated source directly if it fails.

Do not use `repair-drawio` as a routine step for newly generated diagrams. If a new file needs repair, the generation structure was wrong and should be corrected.

## Composite Label and Text Source Rules

Source text structure is part of `.drawio` generation, not a post-export repair strategy. Build or repair the source so Visio does not need to infer meaning from HTML label structure.

- Put overlay text in its own visible `mxCell`.
- Put title text in its own `mxCell` when it needs reliable bold styling.
- Put description text in its own `mxCell` when it should remain normal weight.
- For labels that mix a bold title and normal description, split the title and description into separate text `mxCell`s.
- For colored badge/header/tag elements with white text, put the colored background in a shape with `value=""` and put the white text in a separate text-only `mxCell` above it.
- Use `fontStyle=1` on an `mxCell` whose whole text should stay bold after VSDX export.
- Preserve simple HTML such as `<br>` or basic rich text only when it improves draw.io appearance and does not replace required source-level cells or VSDX character styling.
- Do not use white, hidden, or placeholder text in the main label to reserve space for another overlaid element.
- Mark vertical text, side-axis text, rotated text, connector labels, and intentionally offset labels as special text so export-time `TextXForm` normalization can skip them.

Run `audit-drawio` before VSDX export. If the audit blocks on composite labels, HTML-only bolding, placeholder text, or white-on-color label structure, fix the source contract here. VSDX color normalization and `TextXForm` are export-stage fixes; they do not replace source repair.

## New Diagram Generation

When creating a diagram from requirements:

- Generate `.drawio` directly; do not generate HTML first unless the user explicitly asks for HTML.
- Use the XML skeleton, encoding, structural checks, and VSDX-compatible source rules in this reference.
- Create one page unless the user request clearly requires multiple pages.
- Do not intentionally create risky HTML composite labels and rely on `repair-drawio` as a normal generation step.
- Run `audit-drawio`, export `.drawio` previews for the mapped pages, and fix source issues before VSDX export.

## Draw.io Preview and Stage 1 Gate

Export `.drawio` preview PNGs before VSDX export:

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png --width 2000 -o "out/input.preview.png" "input.drawio"
```

Do not use `-e` for preview PNGs.

For multi-page `.drawio` files, export every page preview:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview-pages input.drawio --width 2000 --stem output
```

This writes `out/output.drawio-page1.png`, `out/output.drawio-page2.png`, and so on. Do not treat the first page preview as validation coverage for the full file.

Use the correct Stage 1 baseline for the input type:

- HTML input: browser-rendered screenshot of the mapped source HTML container.
- Existing `.drawio` input: original `.drawio` page preview.
- Image input: source image or source page.
- New diagram: user-approved design preview or expected design.

Use the visual comparison helper as automatic triage when baseline and candidate images exist:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/visual_compare.py \
  --baseline out/source-preview.png \
  --candidate out/output.drawio-preview.png \
  --mode stage1-html \
  --report out/output.stage1-visual.json \
  --diff out/output.stage1-diff.ppm
```

Use `--mode stage1-drawio`, `stage1-image`, or `stage1-new` for the other input paths. The helper is triage only; inspect `review_required` and `fail` results before deciding whether the gate passes.

## Image Input

When the source is a screenshot or raster diagram, rebuild the diagram as editable draw.io shapes, text, and connectors.

- Use the image as a visual reference for layout, colors, hierarchy, labels, and connectors.
- Do not produce a VSDX that is only a pasted bitmap unless the user explicitly asks for a raster-only result.
- Preserve visual layout and meaningful structure, but prefer clean editable geometry over pixel tracing.
- Map each source image or source page to a draw.io page in the worklist.
- Use the source image or source page as the Stage 1 baseline against the generated `.drawio` preview.

## HTML Input

If the user provides HTML:

1. Search for embedded `<mxfile>`.
2. Search for `<mxGraphModel>`.
3. Search for `data-mxgraph`.
4. Search script blocks for compressed diagram data.
5. Convert the extracted graph to a normal `.drawio`.

If no embedded draw.io graph exists and the HTML itself is the diagram source, rebuild the `.drawio` from DOM and CSS layout semantics:

- Prefer the bundled converter for supported semantic HTML architecture diagrams:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/html_to_drawio.py input.html -o out/input.drawio
```

The converter supports HTML that uses semantic containers such as `figure`, `canvas`, `layer`, `grid`, `card`, `axis`, `bus`, `tech-axis`, `data-flow`, and `desc`. If those containers are missing, do targeted source mapping instead of leaving a one-off conversion script in `out/`.
- Generate a worklist before or immediately after conversion:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist input.html --drawio out/input.drawio
```

- For `.figure`-based HTML, map each figure `id` and figure title to the same-order draw.io page. If the number of figures and draw.io pages differs, stop and repair the mapping before VSDX export.
- Map real containers such as figures, figure headers, canvas/body areas, grids, side axes, cards, buses, legends, and desc/footer panels. Do not infer body elements from header notes, captions, or legends.
- Preserve structural backgrounds and boundaries that communicate grouping, headers, body regions, side axes, and footer/description panels. Decorative-only backgrounds such as repeating gradients, diagonal hatching, subtle page tints, and shadows may be simplified or omitted when they do not change diagram meaning.
- Compute geometry from CSS box-model values: padding, gaps, column counts, and intended boundaries. Aligned sibling regions must share the same `x + width`; never treat a target right boundary as usable width.
- For grid/flex-like track layouts such as `left fixed + gap + flexible center + gap + right fixed`, reserve fixed tracks and gaps before computing the center width. The center/body region must end before the right gap and fixed track; it must not cover side axes, legends, labels, or fixed panels.
- Generate only side axes that exist in the source DOM, and stop each axis at its related body/canvas content rather than footer or description panels.
- For short ASCII labels and technical abbreviations such as `SaaS`, `PaaS`, `DaaS`, `IaaS`, `API`, `B/S`, `TCP`, and `HTTP/HTTPS`, reserve extra width or reduce spacing/font size so Visio Desktop does not wrap text that draw.io kept on one line.
- For technology architecture side labels such as `SaaS/PaaS/DaaS/IaaS`, prefer a wider side-label track and shift/shrink the body track by the same amount. Do not rely on draw.io text metrics for final Visio fit.
- For card body and bus text with mixed Chinese and ASCII technology strings, reserve an additional 4-8 px of height when possible.
- For vertical upright text (`writing-mode: vertical-rl` / `text-orientation: upright`), do not rotate the whole label with `rotation=90`. Use explicit line breaks or separate text cells based on semantic tokens. Split CJK text per character, keep ASCII words, acronyms, protocol names, numbers, and version-like tokens unbroken, and split English phrases by words rather than letters. For example, `数字化` becomes `数\n字\n化`, `Service Layer` becomes `Service\nLayer`, and `SaaS` remains `SaaS`.
- Mark vertical text, side-axis text, rotated text, connector labels, and intentionally offset labels as special text that must be excluded from generic VSDX `TextXForm` normalization.
- Render each source HTML diagram container to its own browser reference screenshot and compare it with the mapped generated `.drawio` page preview before VSDX export. Do not compare an entire long HTML page to a single draw.io page. These browser screenshots are only the HTML-to-drawio Stage 1 baselines. Use `scripts/visual_compare.py --mode stage1-html` as automatic triage when both preview images exist. After Stage 1 passes for every mapped page, use the approved `.drawio` previews as the VSDX/Visio Stage 2 baselines. Fix the `.drawio` source and repeat Stage 1 for up to 3 rounds.
- After conversion, audit diagram count, page mapping, side-axis count, inferred elements, track boundaries, right boundaries, side-axis height, vertical text encoding, and desc/footer overflow before VSDX export.

Do not treat the whole HTML file as a `.drawio`. Do not use a whole-page HTML screenshot as a Stage 1 baseline for one draw.io page when the HTML contains multiple diagrams. If the generated `.drawio` structure differs from the HTML structure, fix the `.drawio` source first; VSDX color and `TextXForm` repair are export-fidelity steps, not substitutes for correcting wrong HTML mapping. If the third HTML-vs-drawio comparison still has major structural differences, stop and report the remaining mismatches instead of exporting a final VSDX. Do not block final delivery only because optional decorative backgrounds were simplified or omitted.
