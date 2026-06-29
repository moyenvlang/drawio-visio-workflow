# VSDX Export Notes

## Required Version

Use draw.io Desktop `26.0.16` for VSDX export.

Newer draw.io Desktop `30.x` CLI builds do not list `vsdx` in supported export formats. If forced, they may write PDF bytes to a `.vsdx` filename. That file is invalid for Visio.

## Windows Paths

Common paths:

- `C:\Program Files\draw.io\draw.io.exe`: often `26.0.16` when installed all-users.
- `%LOCALAPPDATA%\Programs\draw.io\draw.io.exe`: often latest user install.

The workflow supports both native Windows Python and WSL on Windows:

- In native Windows, pass normal absolute Windows paths to draw.io Desktop and Visio COM.
- In WSL, convert Linux paths to Windows-visible paths before calling Windows applications. `/mnt/c/...` should become `C:\...`; other WSL paths should use `wslpath -w` when available.
- Do not hard-code WSL-only path assumptions into commands. Prefer the bundled helper because it performs this path conversion before calling Visio COM.

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
& "C:\Program Files\draw.io\draw.io.exe" -x -f png --width 2000 -o "out/input.preview.png" "input.drawio"
```

Do not use `-e` for preview PNGs.

## VSDX Command

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f vsdx -o "out/output.vsdx" "input.drawio"
```

Keep the original `.drawio` in place. Converted or repaired `.drawio` files, final VSDX files, and preview screenshots belong in the `out/` folder beside the source `.drawio`. Delete temporary files, unused repair passes, comparison pages, unpacked VSDX folders, model XML, and other scratch files after use.

After export, normalize VSDX color cells:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py normalize-vsdx-colors out/output.vsdx
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

## VSDX TextXForm Rule

When Visio shows the shape or text selection box in the correct place but the text itself is offset, treat it as a VSDX `TextXForm` problem. This is common with plain text boxes, wide text boxes, Chinese headings, and title-like labels exported from draw.io.

For text that should fill and center in its shape, normalize these ShapeSheet cells:

```text
TxtPinX    = Width / 2
TxtPinY    = Height / 2
TxtWidth   = Width
TxtHeight  = Height
TxtLocPinX = Width / 2
TxtLocPinY = Height / 2
```

Do not move the shape geometry to fix this. Do not treat it as an HTML layout issue. Do not apply this blindly to connectors, edge labels, rotated text, callouts, intentionally offset annotations, or complex grouped shapes. After changing `TextXForm`, open the VSDX with Microsoft Visio Desktop through COM, export PNG, and compare it with the direct `.drawio` preview.

## Required Round-Trip Visual Check

Do not stop after exporting a valid VSDX package. Visual checks are split into two bounded stages:

- Stage 1: compare the compliant `.drawio` preview with the source preview. The source preview is the rendered HTML screenshot for HTML inputs, the source image for image inputs, the original `.drawio` preview for existing `.drawio` inputs, or the user-approved design preview for new diagrams.
- Stage 2: compare the Visio-rendered PNG with the compliant `.drawio` preview approved by Stage 1.

Each stage may run at most 3 fix-and-compare rounds. If a stage still has material mismatches after round 3, stop and report those mismatches instead of continuing indefinitely or claiming final fidelity.

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png --width 2000 -o "out/input.drawio-preview.png" "input.drawio"
& "C:\Program Files\draw.io\draw.io.exe" -x -f vsdx -o "out/output.vsdx" "input.drawio"
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
$doc = $visio.Documents.Open((Resolve-Path "out/output.vsdx").Path)
$doc.Pages.Item(1).Export((Join-Path (Resolve-Path "out").Path "output.visio-preview.png"))
$doc.Close()
$visio.Quit()
```

Or use the bundled helper:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output --width 2000
```

The helper normalizes VSDX colors and `TextXForm` cells before opening the VSDX with Visio COM for the effect preview.

The helper produces:

- `out/output.vsdx`
- `out/output.drawio-preview.png`
- `out/output.visio-preview.png`

Approval requires Stage 1 and Stage 2 visual comparison. Package validation alone is not enough. Do not retain generated comparison HTML pages; use the source preview, compliant `.drawio` preview, and Visio preview image as the retained review artifacts.

The Visio-rendered preview requires Microsoft Visio Desktop with COM automation available. If Visio COM is unavailable, report that the true Visio effect preview could not be produced; do not silently substitute a draw.io-rendered VSDX PNG for final validation. This applies equally to native Windows and WSL-on-Windows execution.

Do not generate draw.io's VSDX-to-PNG preview as part of the normal workflow. Once Visio COM export is available, draw.io's rendering of a VSDX is redundant and can hide differences that only appear in Microsoft Visio.

Stable, high-fidelity reproduction has higher priority than reducing token usage or saving execution time. Do not skip source audit, Stage 1 `.drawio` preview comparison, VSDX package validation, color normalization, `TextXForm` normalization, Stage 2 Visio COM preview comparison, or final visual comparison solely for speed or token economy.

Also audit important text styling. Some exports keep text position but lose bold weight (`Style=0` in VSDX character rows). For headings such as card titles or layer titles, run:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text out/output.vsdx --text "路线规划应用" --text "数据服务组件"
```

If important labels are not bold in the Visio-rendered preview or the audit reports `bold=False`, treat it as a regression and revise the `.drawio`.

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
- Do not generate or retain draw.io's VSDX-to-PNG rendering as a normal deliverable. Use Microsoft Visio Desktop COM for the VSDX effect preview.

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
mkdir -p out
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio input.drawio -o out/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio out/input.repaired1.drawio -o out/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio out/input.repaired2.drawio -o out/input.repaired3.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired3.drawio
```

Stop as soon as one repaired file passes `audit-drawio`; use that file for preview and export. Keep only the selected repaired `.drawio` in `out/` and delete unused failed repair-pass files. If the third pass still fails, stop automatic repair and perform targeted manual/model edits or report the remaining blockers. Never overwrite the original file.

The helper is conservative: it handles recognizable title/description and overlay/title/description labels, then leaves uncertain cases for manual edits.

After each optimization pass:

1. Run `audit-drawio`; fix failures before final export.
2. Export a compliant `.drawio` PNG preview and compare it against the source preview for up to 3 Stage 1 rounds.
3. Export VSDX.
4. Open the VSDX with Microsoft Visio Desktop through COM and export PNG.
5. Compare the Visio-rendered preview against the compliant `.drawio` preview approved by Stage 1 for up to 3 Stage 2 rounds.
6. Check for missing badges, lost bolding/font weight, shifted text, changed layer spacing, unexpected arrows, and altered title hierarchy.
7. Audit representative important headings with `audit-text` when bold labels matter.
8. Apply local fixes only; do not rebuild the whole diagram unless the user approves a redesign.

## Validation

VSDX is a ZIP package. Validate:

- `[Content_Types].xml`
- `visio/document.xml`
- `visio/pages/page1.xml`

If `file output.vsdx` says `PDF document`, the export is invalid.
