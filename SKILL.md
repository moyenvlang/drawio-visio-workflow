---
name: drawio-visio-workflow
description: Convert flowcharts and architecture diagrams from images, .drawio files, or HTML into high-fidelity Microsoft Visio .vsdx files. Rebuild or optimize VSDX-friendly .drawio sources, generate preview images, preserve the visual design as much as possible, then export true .vsdx files with draw.io Desktop 26.0.16 and validate the result.
---

# Draw.io to Visio Workflow

Use this skill for high-fidelity diagram-to-Visio conversion:

1. Convert an image, existing `.drawio`, HTML diagram source, or embedded HTML diagram data into a VSDX-friendly `.drawio` source.
2. Export a preview image for review.
3. Iterate on the `.drawio` until the user approves the visual result.
4. Export the approved diagram to a real `.vsdx` file with draw.io Desktop `26.0.16`.
5. Validate that the result is a Visio package, not a PDF renamed to `.vsdx`.

## Core Rules

- Generate or rebuild `.drawio` directly. Do not generate HTML first unless the user specifically asks for HTML.
- For image inputs, reconstruct editable diagram structure in `.drawio`; do not deliver a VSDX that is only a pasted bitmap unless the user explicitly asks for a raster-only result.
- Keep the `.drawio` file as the editable source of truth.
- Use pure Base64 in `<diagram>` text: only `A-Z`, `a-z`, `0-9`, `+`, `/`, `=`.
- Do not put uncompressed Chinese/XML text directly inside `<diagram>` when targeting drawon.cn-like importers.
- Do not URL-escape Base64 as `%2B`, `%2F`, or `%3D` for the primary output unless the user specifically asks for a diagrams.net-standard compressed file.
- For HTML inputs, preserve DOM and CSS layout semantics when rebuilding `.drawio`; do not infer diagram body structure from header notes, captions, or legends.
- Preview with PNG before exporting VSDX.
- Export VSDX only with draw.io Desktop `26.0.16`; newer `30.x` CLI builds do not export true VSDX.
- After exporting VSDX, normalize color cells by preserving `V="#RRGGBB"` and adding `F="RGB(r,g,b)"`.
- Keep the original `.drawio` in place; put converted/repaired `.drawio`, VSDX, and preview screenshots in an `out/` folder beside the source `.drawio`.
- Delete temporary files, intermediate files, comparison pages, unpacked folders, and scratch validation outputs after use.
- Use bundled scripts for repeatable conversion work; do not leave one-off conversion scripts in the user's `out/` folder.
- Use one VSDX-compatible source contract for both newly generated and repaired `.drawio` files.
- When optimizing an existing diagram for VSDX, preserve the original visual design and make only targeted compatibility fixes.
- Run `audit-drawio` before final VSDX export; do not deliver final VSDX while high-risk text structures remain.

## Unified Source Contract

Newly generated and repaired diagrams must follow the same VSDX-compatible `.drawio` source rules. A repaired diagram is not a special output format; it is an existing diagram migrated into the same source structure required for new diagrams.

For new diagrams:

- Generate directly against this contract from the start.
- Do not intentionally create risky HTML composite labels and rely on `repair-drawio` as a normal generation step.
- If a new diagram fails `audit-drawio`, fix the generated source locally and rerun the audit.

For existing diagrams:

- First audit the original file.
- If the structure is recognizable, run `repair-drawio` for up to 3 passes.
- Each repair pass must write a new file, run `audit-drawio`, and stop immediately once the audit passes.
- If the third repaired output still fails, stop automatic repair and perform targeted manual/model edits or report the remaining blockers.
- Never overwrite the original file during repair.

The shared source rules are:

- Use a standard `mxfile` containing a compressed `mxGraphModel` payload.
- Store unescaped Base64 in `<diagram>` text.
- Keep unique IDs and valid `parent`, `source`, and `target` references.
- Do not rely only on HTML `<b>` for key headings that must remain bold in Visio; use `fontStyle=1` or independent text cells.
- If one visual unit contains overlay text, title text, descriptive text, multiple font weights, or multiple text colors, split those roles into independent `mxCell`s.
- If text must appear in white or another specific color on a colored background, split the colored background and text into separate `mxCell`s; do not rely on a filled shape's own label color for Visio fidelity.
- Do not use white, hidden, or placeholder text inside a main label to reserve visual space.
- Validate source structure, preview the `.drawio`, run the VSDX round-trip check, and audit representative bold labels before final delivery.

## Output Layout

Use the source `.drawio` file's directory as the root directory. After converting `.drawio` to Visio, keep only necessary deliverables.

Required layout:

- Keep the original `.drawio` file in its original location.
- Put converted or repaired `.drawio` files in `out/`.
- Put exported `.vsdx` files in `out/`.
- Put screenshot and preview image files in `out/`.

Cleanup rule:

- Delete all temporary files after use.
- Do not retain intermediate failed repair passes unless they are the selected repaired `.drawio` deliverable.
- Do not retain comparison HTML pages.
- Do not retain extracted `mxGraphModel` XML, unpacked VSDX folders, validation scratch files, or experimental variants.

If a repaired file becomes the approved editable source, keep it in `out/` with a clear final filename. Never overwrite the original `.drawio`.

## VSDX Visual Preservation Rule

When an existing `.drawio` diagram needs VSDX-friendly optimization, use the minimum-visual-drift principle: preserve the draw.io appearance as much as possible while reducing known VSDX conversion risks. Do not rebuild the diagram into a plain Visio-native style unless the user explicitly asks for a redesign.

Preserve the original visual design:

- Keep the existing layout, layer structure, colors, title hierarchy, card sizing, and overall proportions.
- Keep important visual elements such as colored badges, bold headings, layer sidebars, and section color strips.
- Do not add new arrows, flow lines, relationship labels, or structural elements unless the source diagram already has them or the user asks for them.
- Do not turn an architecture/framework diagram into a process flowchart without explicit instruction.

Apply only targeted VSDX-risk fixes:

- Remove `shadow=1`; shadows can change shape bounds after VSDX export.
- Remove large or percentage rounded corners, especially `arcSize=18` and `arcSize=30`.
- Prefer `rounded=0` for most rectangles when Visio changes corner radius.
- Reduce large `spacing` values, usually to `spacing=4`, to avoid Visio shrinking usable text width.
- Slightly enlarge text boxes or cards when needed to absorb font metric differences.
- Keep stable Chinese fonts such as `Microsoft YaHei`.

Handle rich text conservatively:

- Do not blindly remove all HTML labels. `<b>`, `<br>`, and simple `<font>` markup often define the intended visual hierarchy.
- Preserve key bold text, line breaks, and colors when they are part of the design.
- Remove only hidden placeholder text, excessive HTML hacks, or markup that clearly causes export problems.

VSDX text weight rule:

- Do not rely only on HTML `<b>` for key headings that must remain bold in Visio.
- Use `fontStyle=1` on an `mxCell` whose text should export as bold, or split mixed title/description labels into separate text `mxCell`s.
- For composite labels that mix emphasized title text and normal explanation text, prefer separate `mxCell`s so the title can use `fontStyle=1` and the explanation can remain normal.
- After export, run `audit-text` for representative important headings and require `bold=True`.

Composite label rule:

- If one visual unit contains overlay text, title text, descriptive text, multiple font weights, or multiple text colors, do not rely on a single HTML label to express all of it.
- Split overlay text, titles, and descriptions into independent `mxCell`s when Visio fidelity matters.
- For colored badge/header/tag elements with white text, use one `mxCell` for the colored background with `value=""` and a separate text-only `mxCell` above it with `fontColor=#ffffff` and the required `fontStyle`.
- Avoid white, hidden, or placeholder text inside the main label to reserve space for an overlaid element.
- Keep overlay text only in its own visible shape; keep the main label focused on the main content.
- Do not treat a VSDX rendered back to PNG by draw.io as a complete substitute for a Visio Desktop check; composite rich-text labels are especially likely to differ.

Pre-export audit/block rule:

- Before final VSDX export, audit the source `.drawio` for high-risk text structures.
- Block final delivery if important visual elements still rely on composite HTML labels, HTML-only `<b>`, white/hidden placeholder text, filled-shape label colors for white-on-color text, or `<br>`-based title/description layout.
- Convert blocked elements into separate `mxCell`s: overlay text, title, and description should be independent; titles that must stay bold must use `fontStyle=1`.
- When the structure is recognizable, generate repaired `.drawio` files for up to 3 passes instead of stopping at the first warning.
- If a risky export is still useful for inspection, clearly label it as a risk build and do not call it final.

Handle nested elements carefully:

- Keep colored badges or small overlaid labels if they are part of the design.
- When moving nested shapes, calculate absolute coordinates by recursively summing all parent offsets.
- Do not assume a single `parent` level; bad coordinate math can move badges to unrelated layers.

Use screenshot comparison as part of the iteration:

- Export a PNG preview after each meaningful change.
- Compare the new preview against the original draw.io rendering or screenshot.
- Check layout, badge positions, bold text/font weight, title hierarchy, section colors, card sizing, and unwanted arrows.
- After exporting VSDX, render the VSDX back to PNG and compare it against the `.drawio` preview. This round-trip comparison is required before considering the VSDX acceptable.
- For key labels that should look bold, inspect both the screenshot and the VSDX character style. A VSDX can preserve layout while losing bold weight.
- Fix deviations with local edits; avoid restarting from a full rebuild.

VSDX color formula rule:

- Draw.io may export color cells as hex-only values such as `V="#ffffff"`, which can render incorrectly in Visio Desktop.
- After VSDX export, preserve the original hex `V="#RRGGBB"` and add the Visio ShapeSheet formula `F="RGB(r,g,b)"`.
- Do not delete `V`; Visio Desktop may fail to render when color cells have only `F`.
- Do not replace `V` with `RGB(...)`; this can still render white text as black.
- Apply this to text, fill, line, and other VSDX color cells before final validation.

VSDX TextXForm rule:

- If a shape's selection box is correct but its text renders offset in Visio, check the VSDX `TextXForm`, not the draw.io geometry.
- For normal titles, labels, plain text boxes, wide text boxes, and Chinese headings that should fill and center within their shape, normalize: `TxtPinX=Width/2`, `TxtPinY=Height/2`, `TxtWidth=Width`, `TxtHeight=Height`, `TxtLocPinX=Width/2`, `TxtLocPinY=Height/2`.
- Do not apply this blindly to vertical text, side-axis text, connectors, edge labels, rotated text, callouts, intentionally offset annotations, or complex grouped shapes.
- After changing `TextXForm`, render the VSDX back to PNG and compare it with the `.drawio` preview.

HTML-to-drawio structure rule:

- HTML-source rebuilds are not exempt from the Unified Source Contract. The generated `.drawio` must use the same compressed Base64 `mxGraphModel` format, text-cell splitting rules, ID/reference validation, `audit-drawio` gate, preview comparison, and VSDX round-trip checks as every other source path.
- HTML-to-drawio conversion must preserve DOM and CSS layout semantics, not just approximate the screenshot. Map real containers such as figures, canvas/body areas, grids, side axes, cards, buses, and desc/footer panels.
- Compute geometry from the CSS box model: container padding, gaps, column counts, and intended boundaries. Aligned sibling regions must share the same `x + width`; never treat a target right boundary as usable width.
- For grid/flex-like track layouts with fixed side columns and a flexible center, reserve fixed tracks and gaps first, then give only the remaining width to the center/body region. The center region must not overlap a right-side axis, label, legend, or fixed panel.
- Side axes must match the source DOM exactly and stop at their related body/canvas content, not footer or description panels.
- For vertical upright text (`writing-mode: vertical-rl` / `text-orientation: upright`), use explicit per-character line breaks or separate text cells; do not rely on narrow text boxes or automatic Chinese wrapping.
- For HTML-to-drawio conversion, render the source HTML to a reference screenshot and compare it with the generated `.drawio` PNG preview before VSDX export. Fix the `.drawio` source and repeat for up to 3 rounds; if the third round still has major visual differences, stop and report the mismatches instead of exporting a final VSDX.
- After HTML-to-drawio conversion, audit diagram count, side-axis count, inferred elements, right boundaries, side-axis height, vertical text encoding, and desc/footer overflow before VSDX export.
- If the generated `.drawio` structure differs from the HTML structure, fix the `.drawio` source first. VSDX color and `TextXForm` repair are export-fidelity steps, not substitutes for correcting wrong HTML mapping.

## Required Two-Step Contract

This skill may include requirement gathering, visual design, preview generation, review loops, and troubleshooting, but it must always contain these two technical steps when producing Visio output.

### Step 1: Generate `.drawio`

The generated file must be a standard draw.io file:

- Root node is `<mxfile>`.
- It contains at least one `<diagram>`.
- Diagram content decodes to an `mxGraphModel`.
- The graph includes required root cells:
  - `<mxCell id="0"/>`
  - `<mxCell id="1" parent="0"/>`

The `<diagram>` payload must be compatible with drawon.cn-like importers:

- Use unescaped, compressed Base64 text.
- Allowed characters are only `A-Z`, `a-z`, `0-9`, `+`, `/`, `=`.
- Do not put uncompressed XML containing Chinese text directly inside `<diagram>`.
- Do not use URL-escaped Base64 such as `%2B`, `%2F`, or `%3D`.

The graph structure must be valid:

- Every edge has explicit `source` and `target`.
- Every `source` and `target` references an existing `mxCell`.
- Every `parent` references an existing `mxCell`.
- IDs are unique.
- IDs `0` and `1` are not reused as business nodes.

If the input source is HTML:

- Extract embedded draw.io data first.
- Check common locations: `<mxfile>`, `<mxGraphModel>`, `data-mxgraph`, compressed diagram payloads, or script-embedded graph data.
- If embedded draw.io data exists, convert the extracted graph into a `.drawio` file.
- If the HTML itself is the diagram source, rebuild `.drawio` from the DOM and CSS layout semantics; do not use only a screenshot-like visual approximation.
- Do not treat the whole HTML document as `.drawio`.

Validate after generation:

- XML parses successfully.
- `<diagram>` content is pure Base64.
- Base64 decodes successfully.
- Decoded bytes raw-deflate decompress successfully.
- Decompressed content is valid `mxGraphModel`.
- No duplicate IDs exist.
- Edge `source` and `target` references exist.
- No invalid `parent` references exist.

### Step 2: Export VSDX with draw.io CLI

Use draw.io Desktop `26.0.16` for VSDX export:

- Preferred Windows path: `C:\Program Files\draw.io\draw.io.exe`.
- Verify version before export:

```powershell
& "C:\Program Files\draw.io\draw.io.exe" --version
```

Expected output:

```text
26.0.16
```

Do not use draw.io `30.x` for VSDX export:

- `30.x` CLI does not support true VSDX export.
- If forced with `-f vsdx`, it may write PDF bytes to a `.vsdx` filename.
- PDF-content `.vsdx` files are invalid and must not be delivered.

Export command:

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f vsdx -o "output.vsdx" "input.drawio"
```

Normalize VSDX colors after export:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py normalize-vsdx-colors output.vsdx
```

Validate after export:

- `file` should report `Microsoft Visio 2013+`.
- The `.vsdx` is a ZIP package.
- It contains:
  - `[Content_Types].xml`
  - `visio/document.xml`
  - `visio/pages/page1.xml`

If validation shows `PDF document`, delete the file and re-export with draw.io Desktop `26.0.16`.

## Workflow

### 1. Gather Requirements

Proceed when the user provides enough detail. Ask only if missing information blocks a useful diagram:

- Diagram type: flowchart, architecture/framework, process, system relationship, deployment, data flow.
- Main nodes, layers, actors, systems, decisions, or relationships.
- Preferred output name or location, if any.

Use the current working directory by default.

### 2. Generate `.drawio`

Build an `mxGraphModel` with:

- `<mxCell id="0"/>`
- `<mxCell id="1" parent="0"/>`
- Business nodes starting from `id="2"` or stable readable ids.
- Every vertex has valid `parent`, geometry, and style.
- Every edge has valid `source` and `target`.
- Text and visual units follow the Unified Source Contract above; new diagrams should not need `repair-drawio` as a normal step.

Then encode the model as draw.io's compressed diagram payload:

1. URL-quote the `mxGraphModel` XML.
2. Raw-deflate compress with `wbits=-15`.
3. Base64 encode.
4. Store the unescaped Base64 string directly in `<diagram>`.

Use `scripts/drawio_codec.py` to wrap or validate generated models:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_codec.py wrap model.xml -o output.drawio --name "Page-1"
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_codec.py validate output.drawio
```

If converting from HTML, first extract the embedded `mxfile`, `mxGraphModel`, `data-mxgraph`, or compressed diagram payload, then write a normal `.drawio`.
If no embedded draw.io graph exists, rebuild from the HTML DOM/CSS structure with `scripts/html_to_drawio.py` when the HTML uses supported semantic diagram containers; otherwise perform targeted source mapping and follow the HTML-to-drawio structure rule above.
For HTML-source rebuilds, compare the source HTML screenshot against the `.drawio` preview and iterate the `.drawio` source for up to 3 rounds before proceeding to VSDX export.

Before VSDX export, audit the source for high-risk text structures:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio input.drawio
```

If this fails on a newly generated file, fix the generated `.drawio` source directly before final export. Use `--allow-risky` only for a clearly marked risk build.

For existing files with common composite labels, repair for up to 3 passes. Each pass writes a new file, audits it, and stops as soon as the audit passes:

```bash
mkdir -p out
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio input.drawio -o out/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio out/input.repaired1.drawio -o out/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio out/input.repaired2.drawio -o out/input.repaired3.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired3.drawio
```

Use the first repaired `.drawio` that passes audit for preview and VSDX export. Keep only the selected repaired `.drawio` in `out/`; delete unused failed repair-pass files. If the third pass still fails, stop automatic repair and do targeted manual/model edits or report the remaining blockers.

### 3. Preview

Check/install draw.io Desktop `26.0.16`, then export PNG:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000
```

Show the preview path to the user. If image viewing is available, inspect the PNG for:

- clipped text
- overlapping nodes
- missing arrows
- off-canvas content
- incorrect layer/order
- unreadable labels

Apply targeted `.drawio` edits and regenerate the preview until approved.

For existing diagrams, preview comparison is mandatory before VSDX export. Keep the latest preview next to the original draw.io screenshot or prior preview and check for visual drift. If the optimized preview loses badges, bold text/font weight, title hierarchy, layout density, or adds arrows that were not present before, revert that specific change and apply a smaller compatibility fix.

For HTML-source rebuilds, the first preview comparison must be against the rendered source HTML screenshot. If the `.drawio` preview remains materially different after 3 source-fix rounds, stop and report the remaining differences instead of exporting a final VSDX.

### 4. Export VSDX

Use only draw.io Desktop `26.0.16`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio -o output.vsdx
```

`export-vsdx` normalizes VSDX color cells after export by preserving hex `V` values and adding `F="RGB(...)"`.

For deliverable VSDX work, prefer the full round-trip command:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output-name --width 2000
```

This generates:

- `out/output-name.vsdx`: final normalized Visio file.
- `out/output-name.drawio-preview.png`: direct `.drawio` PNG preview.
- `out/output-name.vsdx-preview.png`: PNG rendered from the exported VSDX.

Compare the two preview images before approval. If the VSDX-rendered preview differs materially from the `.drawio` preview, edit the `.drawio`, rerun the round-trip check, and only then deliver the VSDX.

`roundtrip-check` runs `audit-drawio` first. If it fails, do not bypass it for a final deliverable. `--allow-risky` is only for producing a temporary risk build for inspection.

For diagrams with visually important bold labels, audit representative text after export. This catches cases where draw.io displays HTML `<b>` correctly but the VSDX stores the same text as `Style=0` / `bold=False`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text output.vsdx --text "路线规划应用" --text "数据服务组件"
```

Treat missing bold style on important headings as a visual regression. Fix the `.drawio` source or styling, rerun the round-trip check, and do not rely only on VSDX package validation.

The script locates `26.0.16`; on Windows it installs it with `winget` when missing:

```powershell
winget install --id JGraph.Draw --exact --version 26.0.16 --accept-package-agreements --accept-source-agreements --silent --force
```

It may coexist with newer draw.io versions. Prefer:

- `C:\Program Files\draw.io\draw.io.exe` for `26.0.16`
- `%LOCALAPPDATA%\Programs\draw.io\draw.io.exe` often points to newer user installs

### 5. Validate VSDX

Always validate after export:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py validate-vsdx output.vsdx
```

A real VSDX is a ZIP package containing at least:

- `[Content_Types].xml`
- `visio/document.xml`
- `visio/pages/page1.xml`

If the file command reports `PDF document`, delete it and re-export using draw.io `26.0.16`. Do not deliver PDF-content files with a `.vsdx` extension.

Package validation is necessary but not sufficient. A structurally valid VSDX can still look wrong in Visio. Always include the VSDX-to-PNG rendered preview in the review loop.

## Useful References

- Read `references/drawio-generation.md` when rebuilding a diagram from an image, converting HTML to `.drawio`, or creating VSDX-friendly `.drawio` structure.
- Read `references/vsdx-export.md` when troubleshooting CLI installation, preview export, or VSDX validation.

## Final Response

Report only the useful artifacts:

- final `.drawio` source path, if generated or changed
- final `.vsdx` path, if exported
- preview image path in `out/`, if generated
- VSDX-rendered preview path in `out/`, if generated
- draw.io CLI version used
- short validation result
