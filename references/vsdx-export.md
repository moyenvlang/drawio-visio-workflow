# VSDX Export Notes

## Required Version

Use draw.io Desktop `26.0.16` for VSDX export.

Newer draw.io Desktop `30.x` CLI builds do not list `vsdx` in supported export formats. If forced, they may write PDF bytes to a `.vsdx` filename. That file is invalid for Visio.

## Windows Paths

Common paths:

- `C:\Program Files\draw.io\draw.io.exe`: often `26.0.16` when installed all-users.
- `%LOCALAPPDATA%\Programs\draw.io\draw.io.exe`: often latest user install.

Always run:

```powershell
& "C:\Program Files\draw.io\draw.io.exe" --version
```

Expected:

```text
26.0.16
```

## Preview Command

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png --width 2000 -o "temp/input.preview.png" "input.drawio"
```

Do not use `-e` for preview PNGs.

## VSDX Command

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f vsdx -o "output.vsdx" "input.drawio"
```

Final VSDX files belong beside the source `.drawio`. Process files such as previews, comparison HTML, repair passes, unpacked VSDX folders, and model XML belong in the `temp/` folder beside that same source `.drawio`.

After export, normalize VSDX color cells:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py normalize-vsdx-colors output.vsdx
```

## VSDX Color Formula Rule

Draw.io may export colors as hex-only cell values, for example:

```xml
<Cell N="Color" V="#ffffff"/>
```

This can render incorrectly in Visio Desktop, especially white text on colored backgrounds. Normalize color cells by preserving the original hex `V` value and adding a Visio ShapeSheet RGB formula:

```xml
<Cell N="Color" V="#ffffff" F="RGB(255,255,255)"/>
```

Rules:

- Preserve `V="#RRGGBB"`.
- Add `F="RGB(r,g,b)"`.
- Do not delete `V`; color cells with only `F` may fail to render.
- Do not replace `V` with `RGB(...)`; this can still render white text as black.
- Apply to text, fill, line, gradient, and other VSDX color cells before final validation.

## Required Round-Trip Visual Check

Do not stop after exporting a valid VSDX package. Render the exported VSDX back to PNG and compare it with the direct `.drawio` PNG preview:

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png --width 2000 -o "temp/input.drawio-preview.png" "input.drawio"
& "C:\Program Files\draw.io\draw.io.exe" -x -f vsdx -o "output.vsdx" "input.drawio"
& "C:\Program Files\draw.io\draw.io.exe" -x -f png --width 2000 -o "temp/output.vsdx-preview.png" "output.vsdx"
```

Or use the bundled helper:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output --width 2000
```

The helper normalizes VSDX colors before rendering the VSDX preview.

The helper produces:

- `output.vsdx` beside the source `.drawio`
- `temp/output.drawio-preview.png`
- `temp/output.vsdx-preview.png`
- `temp/output.compare.html`

Approval requires visual comparison of the direct `.drawio` preview and the VSDX-rendered preview. Package validation alone is not enough.

Also audit important text styling. Some exports keep text position but lose bold weight (`Style=0` in VSDX character rows). For headings such as card titles or layer titles, run:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text output.vsdx --text "路线规划应用" --text "数据服务组件"
```

If important labels are not bold in the VSDX-rendered preview or the audit reports `bold=False`, treat it as a regression and revise the `.drawio`.

## VSDX-Friendly Optimization Rule

Use minimum visual drift when preparing an existing `.drawio` for VSDX:

- Preserve the original layout, colors, badges, bold headings, sidebars, and card structure.
- Do not add arrows or relationship labels unless they already exist or the user asks for them.
- Remove only known conversion risks: shadows, large rounded corners, excessive spacing, and insufficient text box size.
- Keep simple rich text that carries visual meaning, such as `<b>`, `<br>`, and basic font color/size.
- Remove hidden placeholder text or complex HTML hacks only when they affect conversion.
- For nested badges or labels, compute absolute coordinates through all parent containers before repositioning.

Use one source contract for both newly generated and repaired diagrams. New diagrams must be generated directly into the VSDX-compatible source structure. Existing diagrams may be repaired into that same structure; repaired files are not a separate output type.

## Text Weight Rule

Do not rely only on HTML `<b>` for key headings that must remain bold in Visio. Draw.io may render the text as bold while the exported VSDX stores it as `Style=0` / `bold=False`.

Use one of these approaches:

- Set `fontStyle=1` on an `mxCell` whose whole text should be bold.
- For labels that mix a bold title and normal description, split the title and description into separate text `mxCell`s.
- Preserve simple HTML only when it improves draw.io appearance and does not replace required VSDX character styling.
- Run `audit-text` on representative headings after export and require `bold=True`.

## Composite Label Rule

If one visual unit contains overlay text, title text, descriptive text, multiple font weights, or multiple text colors, do not rely on a single HTML label to express all of it. Draw.io and Visio Desktop may interpret the exported text runs, line breaks, colors, and stacking order differently.

Use this structure when Visio fidelity matters:

- Put overlay text in its own visible `mxCell`.
- Put title text in its own `mxCell` when it needs reliable bold styling.
- Put description text in its own `mxCell` when it should remain normal weight.
- For colored badge/header/tag elements with white text, put the colored background in a shape with `value=""` and put the white text in a separate text-only `mxCell` above it.
- Do not use white, hidden, or placeholder text in the main label to reserve visual space for another overlaid element.
- Do not treat draw.io's VSDX-to-PNG rendering as a complete substitute for opening/checking the file in Visio Desktop.

## Pre-Export Audit and Blocking

Before final VSDX export, audit the `.drawio` source:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio input.drawio
```

Block final delivery if important visual elements still rely on:

- composite HTML labels
- HTML-only `<b>` without `fontStyle=1`
- white, hidden, or placeholder text
- filled-shape label colors for white-on-color text
- `<br>`-based title/description layout in one text box

Fix blocked elements by splitting overlay text, title text, and description text into independent `mxCell`s. Use `fontStyle=1` for titles that must stay bold in Visio. If a risky file is still useful for inspection, generate it only as a clearly marked risk build.

For common composite labels, use the bundled repair helper to create new `.drawio` files for up to 3 passes:

```bash
mkdir -p temp
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio input.drawio -o temp/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio temp/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio temp/input.repaired1.drawio -o temp/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio temp/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio temp/input.repaired2.drawio -o temp/input.repaired3.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio temp/input.repaired3.drawio
```

Stop as soon as one repaired file passes `audit-drawio`; use that file for preview and export. If it becomes the approved editable source, write a final `.drawio` beside the original. If the third pass still fails, stop automatic repair and perform targeted manual/model edits or report the remaining blockers. Never overwrite the original file.

The helper is conservative: it handles recognizable title/description and overlay/title/description labels, then leaves uncertain cases for manual edits.

After each optimization pass:

1. Run `audit-drawio`; fix failures before final export.
2. Export a PNG preview.
3. Export VSDX.
4. Render the VSDX back to PNG.
5. Compare the original draw.io preview, previous approved preview, and VSDX-rendered preview.
6. Check for missing badges, lost bolding/font weight, shifted text, changed layer spacing, unexpected arrows, and altered title hierarchy.
7. Audit representative important headings with `audit-text` when bold labels matter.
8. Apply local fixes only; do not rebuild the whole diagram unless the user approves a redesign.

## Validation

VSDX is a ZIP package. Validate:

- `[Content_Types].xml`
- `visio/document.xml`
- `visio/pages/page1.xml`

If `file output.vsdx` says `PDF document`, the export is invalid.
