# VSDX Export Notes

## Required Version

Use draw.io Desktop `26.0.16` for preview, VSDX export, and round-trip checks.

Newer draw.io Desktop `30.x` CLI builds do not list `vsdx` in supported export formats. If forced, they may write PDF bytes to a `.vsdx` filename. That file is invalid for Visio.

Dependency behavior:

- draw.io Desktop `26.0.16` is a blocking dependency only for commands that actually need draw.io: `preview`, `preview-pages`, `export-vsdx`, and `roundtrip-check`.
- Those commands may automatically install only the fixed draw.io version, and only on native Windows Python or WSL with `powershell.exe` and `winget`.
- Use `--no-install` on `ensure`, `preview`, `preview-pages`, `export-vsdx`, or `roundtrip-check` to forbid automatic installation.
- If `winget` or PowerShell is unavailable, stop and provide the manual fixed-version install command. Do not guess macOS, Linux, snap, flatpak, or Homebrew commands.
- Visio Desktop COM is a degraded validation dependency. If it is unavailable, VSDX export can still complete, but true Visio-rendered preview validation must be reported as unavailable.

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

Direct `.drawio` preview export and Stage 1 baseline comparison are owned by `references/drawio-generation.md`. This reference uses the Stage 1-approved `.drawio` preview only as the Stage 2 VSDX baseline.

## VSDX Command

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f vsdx -o "out/output.vsdx" "input.drawio"
```

Keep the original `.drawio` in place. Final VSDX files, Visio previews, package validation scratch, and Stage 2 comparison artifacts belong in the `out/` folder beside the source `.drawio`. Source `.drawio` generation, repair, image reconstruction, HTML mapping, and draw.io preview rules are owned by `references/drawio-generation.md`.

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

Do not stop after exporting a valid VSDX package. Visual checks are split into two bounded stages. Stage 1 depends on the input type; Stage 2 always uses the Stage 1-approved `.drawio` preview as the baseline.

Before VSDX export, complete the source-side worklist, `.drawio` previews, and Stage 1 approval described in `references/drawio-generation.md`. The worklist defines the source page/container to draw.io page mapping. For multi-page files, every Stage 2 check is per-page and must use that same mapping.

- Stage 2 for all inputs (`draw.io -> VSDX`): compare each Visio-rendered PNG with the mapped compliant `.drawio` preview approved by Stage 1.

Stage 2 should preserve the approved draw.io rendering; do not re-baseline Stage 2 against the original HTML, image, original `.drawio`, or design brief. Stage 1 source fidelity rules are owned by `references/drawio-generation.md`.

Stage 2 may run at most 3 fix-and-compare rounds per affected page. If it still has material mismatches after round 3, stop and report those mismatches instead of continuing indefinitely or claiming final fidelity.

Use the visual comparison helper as an automatic triage step when baseline and candidate images are available:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/visual_compare.py \
  --baseline out/output.drawio-preview.png \
  --candidate out/output.visio-preview.png \
  --mode stage2-vsdx \
  --report out/output.stage2-visual.json \
  --diff out/output.stage2-diff.ppm
```

The helper supports common non-interlaced 8-bit PNG files, PPM files, and any extra formats available through Python's stdlib tkinter build. It returns `pass`, `review_required`, or `fail`. It trims outer background margins by default; add `--no-crop` when page-level placement or whitespace is part of the requirement. Treat `fail` as an inspection trigger. It blocks final delivery only when manual review confirms structural drift, missing text, color loss, clipping, text offset, or material layout shifts. Renderer antialiasing, small line-weight changes, and harmless font rasterization differences alone do not block delivery. Treat `review_required` as a prompt to inspect the diff image and the baseline/candidate previews; do not count it as automatic approval.

For a manual one-page Visio COM preview after VSDX export:

```powershell
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
$doc = $visio.Documents.Open((Resolve-Path "out/output.vsdx").Path)
$doc.Pages.Item(1).Export((Join-Path (Resolve-Path "out").Path "output.visio-preview.png"))
$doc.Close()
$visio.Quit()
```

For multi-page VSDX files, use the bundled helper:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visio-preview-pages out/output.vsdx --stem output
```

This writes `out/output.visio-page1.png`, `out/output.visio-page2.png`, and so on.

After Stage 1 has been completed and the `.drawio` preview is approved, use the bundled helper to generate Stage 2 artifacts:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output --width 2000
```

The helper normalizes VSDX colors and `TextXForm` cells before opening the VSDX with Visio COM for the effect preview. It does not perform the input-specific Stage 1 comparison against the HTML screenshot, source image, original `.drawio` preview, or user-approved design; complete that comparison separately before treating its output as final.

The helper produces:

- `out/output.vsdx`
- `out/output.drawio-preview.png`
- `out/output.visio-preview.png`

Approval requires completed Stage 1 source approval from `references/drawio-generation.md` and Stage 2 Visio comparison for every mapped page. Package validation, `roundtrip-check` output, and `visual_compare.py` output alone are not enough. For multi-page files, prefer `export-vsdx`, `preview-pages`, and `visio-preview-pages`; `roundtrip-check` is a targeted single-page helper unless run separately for each relevant page. Do not retain generated comparison HTML pages; use the source preview, compliant `.drawio` preview, Visio preview image, worklist, and optional visual comparison report/diff image as the retained review artifacts.

The Visio-rendered preview requires Microsoft Visio Desktop with COM automation available. If Visio COM is unavailable, report that the true Visio effect preview could not be produced; do not silently substitute a draw.io-rendered VSDX PNG for final validation. This applies equally to native Windows and WSL-on-Windows execution.

Do not generate draw.io's VSDX-to-PNG preview as part of the normal workflow. Once Visio COM export is available, draw.io's rendering of a VSDX is redundant and can hide differences that only appear in Microsoft Visio.

Stable, high-fidelity reproduction has higher priority than reducing token usage or saving execution time. Do not skip source audit, worklist/page mapping, Stage 1 `.drawio` preview comparison, VSDX package validation, color normalization, `TextXForm` normalization, Stage 2 Visio COM preview comparison, or final visual comparison solely for speed or token economy.

Also audit important text styling. Some exports keep text position but lose bold weight (`Style=0` in VSDX character rows). For headings such as card titles or layer titles, run:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text out/output.vsdx --text "路线规划应用" --text "数据服务组件"
```

If important labels are not bold in the Visio-rendered preview or the audit reports `bold=False`, treat it as a regression. Revise the `.drawio` according to the composite label and text source rules in `references/drawio-generation.md`, then re-export and rerun Stage 2.

## VSDX-Friendly Optimization Rule

Use minimum visual drift when preparing an existing `.drawio` for VSDX, but keep the source optimization rules in one place: follow `references/drawio-generation.md` for the unified source contract, composite label splitting, nested element handling, HTML/image/new diagram reconstruction, and pre-export `audit-drawio` blocking rules. This reference only owns what happens after a compliant `.drawio` is ready for export.

## Text Weight Rule

Draw.io may render an HTML `<b>` label as bold while the exported VSDX stores it as `Style=0` / `bold=False`. The source-side fix is defined in `references/drawio-generation.md`: use `fontStyle=1` or split mixed labels into independent text cells. This export reference owns only the VSDX verification step: run `audit-text` on representative headings after export and require `bold=True`.

## Composite Label Rule

Composite label, overlay text, title/description splitting, white-on-color text, and placeholder-text prohibitions are source rules owned by `references/drawio-generation.md`. Before export, require `audit-drawio` to pass. After export, verify the resulting VSDX through Visio COM and `audit-text`; do not generate or retain draw.io's VSDX-to-PNG rendering as a normal deliverable.

## Pre-Export Audit and Blocking

Before final VSDX export, audit the `.drawio` source:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio input.drawio
```

Block final delivery if `audit-drawio` reports high-risk source structures. The exact blocked structures and source fixes are defined in `references/drawio-generation.md`. If a risky file is still useful for inspection, generate it only as a clearly marked risk build.

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

After each export-fidelity pass:

1. Run `audit-drawio`; fix failures before final export.
2. Confirm the Stage 1-approved `.drawio` preview exists for every mapped page.
3. Export VSDX with draw.io Desktop `26.0.16`.
4. Normalize VSDX colors and `TextXForm` cells where applicable.
5. Validate the VSDX package.
6. Open the VSDX with Microsoft Visio Desktop through COM and export PNG previews for every mapped page.
7. Compare each Visio-rendered preview against the compliant `.drawio` preview approved by Stage 1 for up to 3 Stage 2 rounds per affected page.
8. Check for missing badges, lost bolding/font weight, shifted text, changed layer spacing, unexpected arrows, and altered title hierarchy.
9. Audit representative important headings with `audit-text` when bold labels matter.
10. Apply local fixes only; do not rebuild the whole diagram unless the user approves a redesign.

## Validation

VSDX is a ZIP package. Validate:

- `[Content_Types].xml`
- `visio/document.xml`
- `visio/pages/page1.xml`

If `file output.vsdx` says `PDF document`, the export is invalid.
