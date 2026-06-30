---
name: drawio-visio-workflow
description: Convert flowcharts and architecture diagrams from images, .drawio files, or HTML into high-fidelity Microsoft Visio .vsdx files. Rebuild or optimize VSDX-friendly .drawio sources, generate preview images, preserve the visual design as much as possible, then export true .vsdx files with draw.io Desktop 26.0.16 and validate the result.
---

# Draw.io to Visio Workflow

Use this skill to convert images, existing `.drawio` files, HTML diagrams, or embedded draw.io data into high-fidelity, editable Microsoft Visio `.vsdx` files.

The `.drawio` file is always the editable source of truth. The `.vsdx` is the final Visio deliverable.

## Required Reference Routing

Before doing conversion work, read the reference file that owns the detailed procedure for the current task:

- Read `references/drawio-generation.md` when creating or repairing `.drawio`, rebuilding from an image, converting HTML, extracting embedded draw.io data, applying the VSDX-compatible source contract, or troubleshooting Stage 1 source-to-draw.io mismatches.
- Read `references/vsdx-export.md` before preview/export work, draw.io Desktop setup, VSDX validation, color normalization, `TextXForm` repair, Visio COM preview, Stage 2 comparison, or VSDX-specific failure handling.
- Use this `SKILL.md` as the required gate checklist. The references provide the detailed implementation rules; they do not relax the preflight, worklist, Stage 1, Stage 2, multi-page, cleanup, or final response requirements below.

## 1. Non-Negotiable Rules

- Keep the original source file unchanged.
- Put converted or repaired `.drawio` files, exported `.vsdx` files, previews, and screenshots in an `out/` folder beside the source.
- Generate or repair `.drawio` directly. Do not generate HTML first unless the user explicitly asks for HTML.
- For image inputs, reconstruct editable diagram structure in `.drawio`; do not deliver a VSDX that is only a pasted bitmap unless the user explicitly asks for a raster-only result.
- Use the same VSDX-compatible source contract for newly generated and repaired `.drawio` files.
- Run `audit-drawio` before final VSDX export; do not deliver a final VSDX while high-risk text structures remain.
- Preview every `.drawio` page as PNG before exporting VSDX. For multi-page inputs, do not treat a first-page preview as coverage for the whole file.
- Use draw.io Desktop `26.0.16` for VSDX export.
- Treat draw.io Desktop `26.0.16` as a blocking dependency for preview, VSDX export, and round-trip checks. `drawio_cli.py ensure` may automatically install only this fixed version, and only on native Windows Python or WSL with `powershell.exe` and `winget`.
- Do not use draw.io `30.x` for final VSDX export. Newer CLI builds may write PDF bytes to a `.vsdx` filename.
- Normalize VSDX color cells after export by preserving `V="#RRGGBB"` and adding `F="RGB(r,g,b)"`.
- Generate the final Visio effect preview by opening the exported `.vsdx` with Microsoft Visio Desktop through COM and exporting PNG.
- Do not silently substitute draw.io-rendered VSDX previews for true Visio Desktop validation.
- If Visio COM is unavailable, report that true Visio effect validation could not be completed.
- Support both native Windows Python and WSL-on-Windows execution. When calling Windows applications from WSL, convert WSL paths to Windows paths.
- Delete temporary files, comparison pages, unpacked folders, validation scratch files, and failed intermediate repair outputs after use.
- Use bundled scripts for repeatable conversion work; do not leave one-off conversion scripts in the user's `out/` folder.

## 2. End-to-End Workflow

### Step 0. Preflight and User Choice

Run preflight before conversion:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preflight --out-dir out
```

Preflight checks draw.io `26.0.16`, Visio COM, Python Playwright Chromium for HTML screenshots, output writability, Chinese paths, and PowerShell logging.

If the environment is incomplete, tell the user briefly:

```text
Environment is incomplete, but conversion may continue.

Missing:
- Visio unavailable: cannot confirm real Visio rendering.
- HTML screenshots unavailable: cannot automatically compare HTML source with conversion output.

Impact:
Continuing can still generate files, but fidelity may be affected, especially text wrapping, position, colors, lines, and layout.

Choose:
1. Fix environment and rerun.
2. Continue conversion, accepting possible fidelity issues.
3. Stop.
```

Rules:

- Stop for blocking items unless the user explicitly chooses a reduced output such as `.drawio` only.
- Continue through degraded items only after the user accepts that fidelity may be affected.
- In non-interactive runs, use `--strict` to stop on any incomplete validation, or `--continue-with-risk` to continue past degraded checks.
- Automatically install only blocking draw.io Desktop `26.0.16`, and only in supported Windows/WSL environments. Do not automatically install degraded or optional dependencies such as Visio COM, Python Playwright, or Chromium; ask the user to install them or continue with reduced validation.

### Step 1. Identify Input Type and Page Mapping

Choose the relevant path from section 3:

- New diagram
- Existing `.drawio`
- HTML source
- Image source

Also identify the page mapping before conversion work starts:

- HTML input: list each semantic diagram container such as `.figure`, its `id`, title, note, and intended draw.io page number.
- Existing `.drawio`: list each `<diagram>` page name and page number.
- Image input: list each source image or source page.
- New diagram: list the requested pages or assume one page when no multi-page requirement exists.

After the input-specific preparation, all paths rejoin the common workflow below.

### Step 2. Prepare Output Directory and Worklist

Create an `out/` folder beside the source file.

Generate a conversion worklist in `out/` before heavy conversion/export work:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist source.html
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist source.html --drawio out/source.drawio
```

This writes both:

- `out/<source>.worklist.json` as the machine-readable source of truth.
- `out/<source>.worklist.md` as the user-readable report.

Update check status as steps complete:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist-update out/source.worklist.json --id audit_drawio --status pass
```

Check:

- The original source file remains in its original location.
- Generated, repaired, and exported deliverables go into `out/`.
- The worklist records source page/container, draw.io page, expected source screenshot, draw.io preview, Visio preview, and required validation checks.
- Scratch files are not retained as deliverables.

Create scratch directories only under `out/.tmp/<run-id>`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py scratch-create --out-dir out
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py scratch-clean out/.tmp/<run-id>
```

Keep scratch files only when a failure needs debugging. On successful delivery, remove scratch files and keep only final `.drawio`, `.vsdx`, previews, and worklist files.

### Step 3. Generate or Repair `.drawio`

Create a VSDX-compatible `.drawio` source that follows the Unified Source Contract in section 4 and the detailed generation rules in `references/drawio-generation.md`.

For generated models, use `scripts/drawio_codec.py` to wrap or validate `mxGraphModel` XML:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_codec.py wrap model.xml -o output.drawio --name "Page-1"
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_codec.py validate output.drawio
```

Step check:

- Root node is `<mxfile>` with at least one `<diagram>`.
- Diagram content is unescaped Base64 whose decoded raw-deflate payload is valid `mxGraphModel`.
- Required root cells exist: `<mxCell id="0"/>` and `<mxCell id="1" parent="0"/>`.
- IDs are unique; business nodes do not reuse IDs `0` or `1`.
- `parent`, `source`, and `target` references are valid.

### Step 4. Audit `.drawio`

Run:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio input.drawio
```

Step check:

- No high-risk composite HTML labels remain.
- Important bold text does not rely only on HTML `<b>`.
- White or specific-color text on a colored background is split into separate background and text cells.
- No hidden, white, or placeholder text is used to reserve layout space.
- Overlay text, title text, descriptive text, multiple font weights, and multiple text colors are split into independent `mxCell`s when Visio fidelity matters.

If the audit fails:

- For new diagrams, fix the generated `.drawio` source directly and rerun the audit.
- For existing diagrams, run `repair-drawio` for up to 3 passes. Use the first repaired file that passes audit.
- If the third repaired output still fails, stop automatic repair and perform targeted manual/model edits or report the remaining blockers.
- Use `--allow-risky` only for a clearly marked risk build, not for a final deliverable.

For targeted geometry, value, or style edits, use the bundled patch tool instead of one-off decode/edit/re-encode scripts:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py patch-drawio out/input.drawio \
  --page 3 \
  --match-text "SaaS" \
  --match-style-contains techlabel \
  --set x=36 --set width=84 \
  -o out/input.patched.drawio
```

Useful options:

- `--list-matches` to inspect matched cells.
- `--dry-run` to show matches without writing.
- `--match-id`, `--match-text`, `--match-value-regex`, and `--match-style-contains` for explicit selection.
- `--set-style key=value` and `--delete-style key` for style changes.

### Step 5. Export `.drawio` Preview

Check or install draw.io Desktop `26.0.16`, then export PNG. Use `references/vsdx-export.md` for the detailed CLI/version behavior. Default `ensure` may auto-install the fixed version only on native Windows Python or WSL with `powershell.exe` and `winget`; use `--no-install` for a check-only run.

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure --no-install
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview-pages input.drawio --width 2000
```

Use `preview` for a known single-page file or a targeted one-page check. Use `preview-pages` for any multi-page `.drawio`; it exports one PNG per `<diagram>` page as `out/<stem>.drawio-pageN.png`.

Step check:

- Text is not clipped.
- Nodes do not overlap.
- Arrows are present and correct.
- No unexpected arrows were added.
- Layout, layer order, colors, badges, title hierarchy, card sizing, and proportions look correct.
- Off-canvas content is not present.
- Labels remain readable.

### Step 6. Source-to-Draw.io Preview Gate

This is Stage 1: compare the input-specific source reference against the compliant `.drawio` PNG preview. The source reference depends on the input path; do not apply the HTML screenshot baseline to existing `.drawio` inputs.

For multi-page inputs, Stage 1 is per-page. Every source page/container in the worklist must map to exactly one `.drawio` preview page before VSDX export. Do not compare a full-page HTML screenshot against a single draw.io page preview.

Use the correct baseline for the input type:

- HTML input: capture each semantic diagram container with fixed Python Playwright Chromium screenshots, then compare each screenshot to its mapped generated `.drawio` page preview.
- Existing `.drawio` input: original `.drawio` page preview, then compare it to the mapped repaired or optimized `.drawio` page preview.
- Image input: source image or source page.
- New diagram: user-approved design preview or expected design for the mapped page.

For HTML screenshots, use only the bundled command by default:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py html-capture source.html --selector ".figure" --out out --stem source
```

This command uses Python Playwright Chromium only. If it is unavailable, ask the user to install it or continue with reduced fidelity validation:

```bash
python -m pip install playwright
python -m playwright install chromium
# Linux/WSL only:
python -m playwright install-deps chromium
```

Do not automatically try Windows Chrome, Edge, Node Playwright, or system Chromium in the default flow. Those can be added only as explicit advanced options later.

Optional automatic triage:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py validate-structure \
  --html source.html \
  --drawio out/output.drawio \
  --report out/output.stage1-structure.json

python3 ~/.codex/skills/drawio-visio-workflow/scripts/visual_compare.py \
  --baseline source-preview.png \
  --candidate out/output.drawio-preview.png \
  --mode stage1-html \
  --report out/output.stage1-visual.json \
  --diff out/output.stage1-diff.ppm
```

For HTML inputs, run structure validation even when screenshots are unavailable. It checks page count, key text, main semantic element counts, and page bounds.

Use `--mode stage1-drawio`, `stage1-image`, or `stage1-new` for other input paths. Pixel comparison reports `pass`, `review_required`, or `fail`; it is an automatic first-pass triage and does not replace checking structural elements, text presence, or allowed decorative differences.
By default it trims outer background margins before comparison, which is useful when screenshots have different viewport padding. Add `--no-crop` when page-level alignment or outer whitespace is part of the requirement.

Step check:

- Layout matches the input-specific source reference.
- Card sizes, section boundaries, side axes, legends, and footer regions match where applicable.
- Colors, badges, title hierarchy, and important bold labels match.
- Structural backgrounds and containers that communicate grouping or boundaries are preserved.
- Purely decorative backgrounds such as light gradients, diagonal texture fills, subtle page tints, and shadows may be simplified or omitted when they do not change diagram meaning.
- No structural elements were invented, removed, or moved materially.

Rules:

- If this gate fails, fix the `.drawio` source and regenerate the `.drawio` preview.
- If `visual_compare.py` reports `fail`, inspect the source and candidate previews. Treat it as a gate failure only when structural drift, missing text, color loss, clipping, or material layout shifts are confirmed; font antialiasing and allowed decorative differences alone do not block delivery.
- If `visual_compare.py` reports `review_required`, inspect the diff image and source/candidate previews before deciding whether the gate passes.
- Run at most 3 source-fix rounds.
- If the preview still differs materially after round 3, stop and report the remaining mismatches instead of exporting a final VSDX.
- Do not export final VSDX until this gate passes.

### Step 7. Export VSDX

Use only draw.io Desktop `26.0.16` for VSDX export. Follow `references/vsdx-export.md` for manual CLI commands, Windows/WSL path handling, and the warning that draw.io `30.x` may write PDF bytes to a `.vsdx` filename.

Scripted export:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio -o output.vsdx
```

After the Source-to-Draw.io Preview Gate has passed, prefer the round-trip command to generate the VSDX and Stage 2 preview artifacts:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output-name --width 2000
```

This generates:

- `out/output-name.vsdx`
- `out/output-name.drawio-preview.png`
- `out/output-name.visio-preview.png`

`roundtrip-check` runs `audit-drawio`, exports the `.drawio` preview, exports and validates the VSDX, normalizes VSDX color/TextXForm cells, and exports the Visio COM preview. It does not compare the input-specific Stage 1 baseline against the `.drawio` preview; do that before calling it for a final deliverable. If its audit fails, do not bypass it for a final deliverable.

For multi-page files, use `export-vsdx` plus `preview-pages` and `visio-preview-pages` so every page has explicit Stage 1 and Stage 2 artifacts. `roundtrip-check` is a targeted single-page helper unless run separately for each relevant page.

### Step 8. Normalize and Validate VSDX

`export-vsdx` and `roundtrip-check` normalize VSDX color cells after export. Follow `references/vsdx-export.md` for exact color and package rules. If needed, run normalization directly:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py normalize-vsdx-colors output.vsdx
```

Color rule: preserve `V="#RRGGBB"`, add `F="RGB(r,g,b)"`, do not delete `V`, and do not replace `V` with `RGB(...)`.

Validate:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py validate-vsdx output.vsdx
```

Step check:

- `file` should report `Microsoft Visio 2013+`.
- The `.vsdx` is a ZIP package, not PDF content renamed to `.vsdx`.
- The package contains:
  - `[Content_Types].xml`
  - `visio/document.xml`
  - `visio/pages/page1.xml`

If validation shows `PDF document`, delete the file, confirm draw.io Desktop `26.0.16`, and re-export.

### Step 9. Visio Preview Gate

This is Stage 2: open the exported `.vsdx` with Microsoft Visio Desktop through COM, export PNG, and compare that Visio-rendered PNG against the compliant `.drawio` PNG approved by Stage 1. Stage 2 always uses the approved `.drawio` preview as the baseline, regardless of whether Stage 1 started from HTML, an original `.drawio`, an image, or a new design.

Do not use draw.io's VSDX-to-PNG rendering as the final Visio effect image.

For multi-page VSDX files, export every Visio page:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visio-preview-pages out/output.vsdx --stem output
```

Optional automatic triage:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visual-triage \
  --baseline out/output.drawio-preview.png \
  --candidate out/output.visio-preview.png \
  --mode stage2-vsdx \
  --report out/output.stage2-triage.json \
  --diff out/output.stage2-diff.ppm
```

Stage 2 validation is structure-first. Missing text, missing shapes, severe layout drift, color loss, clipping, or text offset are failures. Pixel differences from antialiasing, font rasterization, and small line-weight changes are review signals, not automatic failures.
Use `--no-crop` when the exported page boundary or absolute page placement must be compared, not just the diagram content.

Step check:

- Text position matches.
- Text color, fill color, and line color match.
- Important bold labels remain bold.
- Shapes have not shifted or resized unexpectedly.
- Text is not offset inside its shape.
- Composite labels, badges, and white-on-color text still render as intended.

Rules:

- If this gate fails, fix `.drawio` compatibility issues first.
- If `visual_compare.py` reports `fail`, inspect the draw.io and Visio previews. Treat it as a Visio Preview Gate failure only when structural drift, missing text, color loss, clipping, text offset, or material layout shifts are confirmed; renderer antialiasing, small line-weight changes, and harmless font rasterization differences alone do not block delivery.
- Apply VSDX color or `TextXForm` fixes when needed.
- Run at most 3 VSDX-fix rounds.
- If the Visio-rendered preview still differs materially after round 3, stop and report the remaining mismatches instead of claiming the VSDX is final.
- If Visio COM is unavailable, report that true Visio effect preview could not be produced.
- PowerShell or COM logs may garble Chinese paths on some machines. Treat file existence and format validation as authoritative. The bundled COM commands print ASCII status lines where possible.

### Step 10. Audit Important Text

For visually important bold labels, inspect both the screenshot and the VSDX character style.

Run:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text output.vsdx --text "Important Heading"
```

Step check:

- Representative important headings are present.
- Headings that must remain bold report `bold=True`.

If bold is missing:

- Do not rely only on HTML `<b>`.
- Split heading text into an independent text `mxCell`.
- Use `fontStyle=1`.
- Rerun the round-trip check and `audit-text`.
- See `references/vsdx-export.md` for the full text weight rule.

### Step 11. Final Delivery Review

This final review checks delivery completeness only. It does not replace the step-level audits above.

Check:

- Original source file was not overwritten.
- Final `.drawio` is in `out/`, if generated or repaired.
- Final `.vsdx` is in `out/`, if exported.
- `.drawio` preview PNG is in `out/`.
- Visio COM preview PNG is in `out/`, or COM unavailability is explicitly reported.
- For multi-page inputs, every mapped page has source baseline, draw.io preview, and Visio COM preview artifacts or a clearly reported reason for omission.
- The conversion worklist exists in `out/` and its required checks are complete or explicitly marked unavailable.
- `audit-drawio` passed, or the file is clearly marked as a risk build.
- `validate-vsdx` passed.
- draw.io Desktop version used was `26.0.16`.
- Temporary files and failed intermediate outputs were removed.

## 3. Input Paths

### A. New Diagram

Use when creating a diagram from requirements.

Steps:

1. Follow `references/drawio-generation.md` and generate `.drawio` directly using the Unified Source Contract.
2. Do not intentionally create risky HTML composite labels and rely on `repair-drawio` as a normal generation step.
3. Run `audit-drawio`, export the `.drawio` preview, pass Stage 1, export and validate VSDX, and pass Stage 2.

### B. Existing `.drawio`

Use when converting or optimizing an existing draw.io file.

Steps:

1. Keep the original file unchanged.
2. Audit the original file and follow the repair/optimization rules in `references/drawio-generation.md` and `references/vsdx-export.md`.
3. If the structure is recognizable and the audit fails, run `repair-drawio` for up to 3 passes.
4. Each repair pass must write a new file, run `audit-drawio`, and stop immediately once the audit passes.
5. Use the first repaired `.drawio` that passes audit for preview and VSDX export.
6. Preserve layout, layer structure, colors, title hierarchy, badges, card sizing, section color strips, and overall proportions; do not add new arrows, flow lines, relationship labels, or structural elements unless the source diagram already has them or the user asks for them.
7. Export the original `.drawio` preview and compare the optimized preview against it.
8. Export and validate VSDX only after the Source-to-Draw.io Preview Gate passes.
9. Compare the Visio-rendered preview against the Stage 1-approved optimized `.drawio` preview.

Repair commands:

```bash
mkdir -p out
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio input.drawio -o out/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired1.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio out/input.repaired1.drawio -o out/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired2.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio out/input.repaired2.drawio -o out/input.repaired3.drawio
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio out/input.repaired3.drawio
```

Keep only the selected repaired `.drawio` in `out/`; delete unused failed repair-pass files. Never overwrite the original `.drawio`.

### C. HTML Source

Use when the source is an HTML diagram.

Steps:

1. Follow the HTML input route in `references/drawio-generation.md`.
2. First look for embedded draw.io data: `<mxfile>`, `<mxGraphModel>`, `data-mxgraph`, compressed diagram payloads, or script-embedded graph data.
3. If embedded draw.io data exists, extract it and convert it into a normal `.drawio`; otherwise rebuild from DOM and CSS layout semantics.
4. Use `scripts/html_to_drawio.py` for supported semantic diagram containers; otherwise perform targeted source mapping.
5. Generate a worklist that maps every semantic diagram container to a draw.io page.
6. Render each source HTML diagram container to a browser reference screenshot; for `.figure`-based HTML, screenshot each figure independently.
7. Use those per-container screenshots only as Stage 1 baselines. After Stage 1 passes for every mapped page, use the compliant `.drawio` previews as Stage 2 baselines.

HTML mapping rules:

- Preserve DOM and CSS layout semantics, structural containers, side axes, cards, buses, legends, desc/footer panels, boundaries, and meaningful backgrounds.
- Compute geometry from the CSS box model; fixed tracks, gaps, aligned right boundaries, side-axis height, and body/canvas boundaries must match the source.
- Reserve enough space for short ASCII technical labels and mixed Chinese/ASCII text so Visio export does not introduce wrapping.
- Encode vertical upright text with explicit line breaks or separate text cells, not whole-label `rotation=90`.
- Do not infer diagram body structure from header notes, captions, or legends.
- After conversion, audit diagram count, page mapping, side-axis count, inferred elements, right boundaries, side-axis height, vertical text encoding, and desc/footer overflow before VSDX export.
- If HTML figure/container count and generated `.drawio` page count differ, stop before VSDX export and repair the mapping or conversion.

### D. Image Source

Use when the source is a screenshot or raster diagram.

Steps:

1. Reconstruct editable shapes, text, and connectors in `.drawio`.
2. Do not default to a bitmap-only VSDX.
3. Use the source image as the Source-to-Draw.io Preview Gate baseline.
4. Preserve visual layout, hierarchy, colors, labels, and connectors.
5. Export and validate VSDX only after the Source-to-Draw.io Preview Gate passes.

## 4. Unified Source Contract

Newly generated and repaired `.drawio` files must follow the same VSDX-compatible source rules. Use `references/drawio-generation.md` for the detailed XML skeleton, HTML extraction, geometry, and text-structure guidance.

Encoding and structure:

- Use a standard `mxfile`.
- Store raw-deflate compressed `mxGraphModel` content in `<diagram>` as pure unescaped Base64 (`A-Z`, `a-z`, `0-9`, `+`, `/`, `=`).
- Do not URL-escape Base64 as `%2B`, `%2F`, or `%3D` for the primary output unless the user specifically asks for a diagrams.net-standard compressed file.
- Do not put uncompressed Chinese/XML text directly inside `<diagram>` when targeting drawon.cn-like importers.
- Keep unique IDs and valid `parent`, `source`, and `target` references; every edge has explicit `source` and `target`.

Text and visual structure:

- Do not rely only on HTML `<b>` for key headings that must remain bold in Visio; use `fontStyle=1` or split mixed title/description labels into separate text `mxCell`s.
- Split overlay text, title text, descriptive text, multiple font weights, multiple text colors, and white-on-color labels into independent `mxCell`s when Visio fidelity matters.
- For colored badge/header/tag elements with white text, use an empty colored background cell and a separate text-only cell above it with explicit `fontColor` and required `fontStyle`.
- Do not use white, hidden, or placeholder text inside a main label to reserve visual space.

Compatibility defaults:

- Remove `shadow=1`; shadows can change shape bounds after VSDX export.
- Prefer `rounded=0` for rectangles when Visio Desktop fidelity is more important than matching draw.io corner radius.
- Reduce large `spacing` values, usually to `spacing=4`, to avoid Visio shrinking usable text width.
- Slightly enlarge text boxes or cards when needed to absorb font metric differences.
- Keep stable Chinese fonts such as `Microsoft YaHei`.

Nested element handling:

- Keep colored badges or small overlaid labels if they are part of the design.
- When moving nested shapes, calculate absolute coordinates by recursively summing all parent offsets.
- Do not assume a single `parent` level.

## 5. VSDX-Specific Rules

Use `references/vsdx-export.md` for the full export, normalization, visual check, text weight, and blocking rules.

### Color Cells

Draw.io may export color cells as hex-only values such as `V="#ffffff"`, which can render incorrectly in Visio Desktop.

Gate: after VSDX export, preserve `V="#RRGGBB"`, add `F="RGB(r,g,b)"`, do not delete `V`, do not replace `V` with `RGB(...)`, and apply this to text, fill, line, and other VSDX color cells before final validation.

### TextXForm

If a shape's selection box is correct but its text renders offset in Visio, check the VSDX `TextXForm`, not only the draw.io geometry.

Gate: for normal titles, labels, plain text boxes, wide text boxes, and Chinese headings that should fill and center within their shape, normalize:

- `TxtPinX=Width/2`
- `TxtPinY=Height/2`
- `TxtWidth=Width`
- `TxtHeight=Height`
- `TxtLocPinX=Width/2`
- `TxtLocPinY=Height/2`

Do not apply this blindly to:

- vertical text, side-axis text, connectors, edge labels, rotated text, callouts, intentionally offset annotations, or complex grouped shapes

After changing `TextXForm`, export a Visio COM PNG preview and compare it with the `.drawio` preview.

## 6. Command Reference

Ensure draw.io Desktop `26.0.16`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure --no-install
```

When draw.io is missing, the default `ensure` command installs only on native Windows Python or WSL with `powershell.exe` and `winget`. Unsupported environments must install manually; do not guess macOS, Linux, snap, flatpak, or Homebrew commands.

Manual Windows install command:

```powershell
winget install --id JGraph.Draw --exact --version 26.0.16 --accept-package-agreements --accept-source-agreements --silent --force
```

Validate `.drawio` encoding:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_codec.py validate input.drawio
```

Audit source structure:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-drawio input.drawio
```

Repair existing `.drawio`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio input.drawio -o out/input.repaired1.drawio
```

Export `.drawio` preview:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview-pages input.drawio --width 2000
```

Generate/update a conversion worklist:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist source.html --drawio out/source.drawio
```

Export VSDX:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio -o output.vsdx
```

Run Stage 2 round-trip artifact generation after Stage 1 approval:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output-name --width 2000
```

Export all Visio-rendered page previews for a multi-page VSDX:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visio-preview-pages out/output.vsdx --stem output-name
```

Normalize VSDX colors:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py normalize-vsdx-colors output.vsdx
```

Validate VSDX package:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py validate-vsdx output.vsdx
```

Run visual comparison triage:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/visual_compare.py \
  --baseline baseline.png \
  --candidate candidate.png \
  --mode stage2-vsdx \
  --report out/visual.json \
  --diff out/visual-diff.ppm
```

Audit important text:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text output.vsdx --text "Important Heading"
```

## 7. Common Failure Handling

### `audit-drawio` Fails

- New diagram: fix the `.drawio` source directly.
- Existing diagram: run `repair-drawio` for up to 3 passes.
- Third pass still fails: stop automatic repair and report blockers or perform targeted manual/model edits.
- Do not call a risky export final. Use `--allow-risky` only for an explicitly labeled risk build.
- See `references/vsdx-export.md` for the pre-export audit and blocking details.

### `.drawio` Preview Differs From Source

- This is a Source-to-Draw.io Preview Gate failure.
- Fix the `.drawio` source.
- Do not export final VSDX.
- Stop after 3 failed rounds and report remaining mismatches.

### VSDX Is Actually PDF Content

- Delete the invalid file.
- Confirm draw.io Desktop version is `26.0.16`.
- Re-export.
- Do not deliver PDF-content files with a `.vsdx` extension.

### Visio Preview Differs From `.drawio` Preview

- This is a Visio Preview Gate failure.
- Fix `.drawio` compatibility first.
- Apply color normalization or `TextXForm` fixes if needed.
- Stop after 3 failed rounds and report remaining mismatches.
- See `references/vsdx-export.md` for Stage 2 comparison and VSDX repair details.

### Bold Text Is Lost

- Do not rely only on HTML `<b>`.
- Split the heading into an independent text cell.
- Use `fontStyle=1`.
- Rerun `roundtrip-check` and `audit-text`.

### Text Is Offset in Visio

- Check VSDX `TextXForm`.
- Normalize text pin and size only for normal labels and headings.
- Do not apply blindly to rotated text, connectors, edge labels, vertical text, side-axis text, or intentional annotations.

## 8. Useful References

- `references/drawio-generation.md`: detailed `.drawio` generation, repair, image rebuild, HTML conversion, source contract, and Stage 1 mapping guidance.
- `references/vsdx-export.md`: detailed draw.io Desktop `26.0.16` setup, preview/export, VSDX validation, color normalization, `TextXForm`, Visio COM preview, text weight, and Stage 2 guidance.

## 9. Final Response

Report only useful artifacts:

- final `.drawio` source path, if generated or changed
- final `.vsdx` path, if exported
- `.drawio` preview image path in `out/`, if generated
- Visio-rendered preview path in `out/`, if generated
- conversion worklist path, if generated
- visual comparison report/diff path, if generated and useful
- draw.io CLI/Desktop version used
- short validation result
