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
- Put only the final validated `.drawio` and final validated `.vsdx` deliverables in an `out/` folder beside the source.
- Put previews, worklists, screenshots, validation reports, visual diff images, failed repair candidates, unpacked packages, and cache files under `out/.tmp/<run-id>/`, not directly in `out/`.
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
- On successful delivery, delete `out/.tmp/<run-id>` and remove the empty `out/.tmp` parent when possible. On failure, keep `out/.tmp/<run-id>` for debugging and report its path.
- Before marking cleanup complete, run deliverables-only final cleanup on `out/`; the root `out/` folder must contain only the final validated `.drawio` and `.vsdx` for the requested stem.
- Use bundled scripts for repeatable conversion work; do not leave one-off conversion scripts in the user's `out/` folder.

## 2. End-to-End Workflow

### Step 0. Preflight and User Choice

Run preflight before conversion with the scope that matches the requested output:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preflight --task roundtrip --out-dir out
```

Use:

- `--task drawio-only` when only generating or repairing `.drawio`.
- `--task preview` when exporting `.drawio` PNG previews.
- `--task html` when converting HTML and checking HTML screenshot baseline capability. Run `--task preview` before exporting `.drawio` previews.
- `--task vsdx` when exporting VSDX but not requiring a Visio COM preview in the same command.
- `--task roundtrip` when producing VSDX plus true Visio-rendered preview validation.

Dependency classes:

| Dependency | Required when | Missing behavior |
|---|---|---|
| draw.io Desktop `26.0.16` | `preview`, `preview-pages`, `export-vsdx`, `roundtrip-check` | Blocking for those steps. `preflight` reports whether fixed-version auto-install is available; the draw.io command itself may auto-install only when it truly needs draw.io, auto-install is not disabled, and native Windows or WSL has `powershell.exe` plus `winget`. Otherwise stop with a manual install command. |
| Visio Desktop COM | True final Visio effect validation | Degraded. VSDX export can continue through `export-vsdx`, but `roundtrip-check`/`visio-preview-pages` cannot complete true Visio rendering without COM. The final response must say true Visio-rendered validation was not completed. Do not auto-install. |
| Python Playwright Chromium | HTML source screenshot baselines | Degraded for HTML conversion. Continue only with user acceptance or non-interactive risk mode; otherwise ask the user to install it. Do not auto-install. |
| Visual diff tooling | Automatic triage reports | Degraded. Manual visual inspection can replace automatic triage if reported. Do not auto-install. |
| `winget` | Automatic draw.io installation | If unavailable, do not guess another installer. Stop and provide the fixed-version manual install command. |
| Bundled Python standard-library scripts | Built-in workflow tools | Not external dependencies. Missing bundled scripts are skill installation errors. |

If preflight reports degraded dependencies, tell the user what installing them adds, what continuing loses, and ask whether to install, continue with reduced validation, or stop. If preflight reports draw.io as installable, continue to the actual draw.io command or run `ensure`; that command may install the fixed version automatically unless `--no-install` is set.

Rules:

- Blocking dependencies may be installed automatically only when the current command cannot proceed without them and the install method is known, version-fixed, and controlled.
- Degraded dependencies must not be installed automatically. Ask the user, or continue only when the user accepts reduced validation.
- In non-interactive runs, `--strict` stops on blocking dependencies or degraded validation dependencies.
- In non-interactive runs, `--continue-with-risk` continues past degraded checks but not blocking draw.io failures.
- Use `--no-install` to forbid automatic installation even for blocking draw.io dependencies.
- If Visio COM is degraded and the user accepts reduced validation, use the `vsdx` scope and `export-vsdx` path; do not run `roundtrip-check` as the degraded path because it is the true Visio preview command.

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

Create a scratch directory and generate a conversion worklist inside it before heavy conversion/export work:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py scratch-create --out-dir out
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist source.html --out-dir out/.tmp/<run-id>
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist source.html --drawio out/source.drawio --out-dir out/.tmp/<run-id>
```

This writes both:

- `out/.tmp/<run-id>/<source>.worklist.json` as the machine-readable source of truth.
- `out/.tmp/<run-id>/<source>.worklist.md` as the user-readable report.

Update check status as steps complete:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist-update out/.tmp/<run-id>/source.worklist.json --id audit_drawio --status pass
```

Check:

- The original source file remains in its original location.
- Only final validated generated/repaired `.drawio` and exported `.vsdx` deliverables go into `out/`.
- The worklist records source page/container, draw.io page, temporary source screenshot baseline, draw.io preview, Visio preview, and required validation checks.
- Scratch files are not retained as deliverables.

Create scratch directories only under `out/.tmp/<run-id>`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py scratch-create --out-dir out
```

Use the created `out/.tmp/<run-id>/` for all Stage 1/Stage 2 previews, worklists, reports, diff files, HTML screenshots, failed repair candidates, and other cache files. Keep scratch files only when a failure needs debugging. On successful delivery, remove scratch files and run `final-clean --deliverables-only` so `out/` keeps only the final validated `.drawio` and `.vsdx`.

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

- Treat this as a source-side gate failure.
- Follow the source repair loop in `references/drawio-generation.md`.
- Use `--allow-risky` only for a clearly marked risk build, not for a final deliverable.

For targeted geometry, value, or style edits, use the bundled patch tool instead of one-off decode/edit/re-encode scripts:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py patch-drawio out/input.drawio \
  --page 3 \
  --match-text "SaaS" \
  --match-style-contains techlabel \
  --set x=36 --set width=84 \
  -o out/.tmp/<run-id>/input.patched.drawio
```

Useful options:

- `--list-matches` to inspect matched cells.
- `--dry-run` to show matches without writing.
- `--match-id`, `--match-text`, `--match-value-regex`, and `--match-style-contains` for explicit selection.
- `--set-style key=value` and `--delete-style key` for style changes.

### Step 5. Export `.drawio` Preview

Check or install draw.io Desktop `26.0.16`, then export PNG. Use `references/vsdx-export.md` for the detailed CLI/version behavior. Preview commands need draw.io and may auto-install only the fixed version in supported Windows/WSL environments; add `--no-install` to force check-only behavior.

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure --no-install
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000 --out-dir out/.tmp/<run-id>
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000 --out-dir out/.tmp/<run-id> --no-install
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview-pages input.drawio --width 2000 --out-dir out/.tmp/<run-id>
```

Use `preview` for a known single-page file or a targeted one-page check. Use `preview-pages` for any multi-page `.drawio`; in the deliverables-only workflow it exports one PNG per `<diagram>` page as `out/.tmp/<run-id>/<stem>.drawio-pageN.png`.

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
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py html-capture source.html --selector ".figure" --out out/.tmp/<run-id> --stem source
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
  --report out/.tmp/<run-id>/output.stage1-structure.json

python3 ~/.codex/skills/drawio-visio-workflow/scripts/visual_compare.py \
  --baseline out/.tmp/<run-id>/source-preview.png \
  --candidate out/.tmp/<run-id>/output.drawio-preview.png \
  --mode stage1-html \
  --report out/.tmp/<run-id>/output.stage1-visual.json \
  --diff out/.tmp/<run-id>/output.stage1-diff.ppm
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
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio -o out/<stem>.vsdx
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio -o out/<stem>.vsdx --no-install
```

When `-o` is only a filename, `export-vsdx` writes that basename to the source file's sibling `out/` directory. Use an explicit `out/<stem>.vsdx` path when documenting final deliverables.

After the Source-to-Draw.io Preview Gate has passed, prefer the round-trip command to generate the VSDX and Stage 2 preview artifacts:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output-name --width 2000 --evidence-dir out/.tmp/<run-id>
```

`roundtrip-check` is called only after Stage 1 source approval, and it does not replace the input-specific Stage 1 comparison. See `references/vsdx-export.md` for its detailed responsibilities and outputs.

If Visio COM is unavailable and the user accepts reduced validation, do not use `roundtrip-check`; run `export-vsdx`, validate/normalize the package, and report that true Visio-rendered validation was not completed.

For multi-page files, use `export-vsdx` plus `preview-pages` and `visio-preview-pages` so every page has explicit Stage 1 and Stage 2 artifacts. `roundtrip-check` is a targeted single-page helper unless run separately for each relevant page.

### Step 8. Normalize and Validate VSDX

Normalize VSDX color cells before final validation. Follow `references/vsdx-export.md` for exact color and package rules. If needed, run normalization directly:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py normalize-vsdx-colors output.vsdx
```

Color gate: VSDX color cells must be normalized before final validation. See `references/vsdx-export.md` for the detailed rule.

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
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visio-preview-pages out/output.vsdx --stem output --out-dir out/.tmp/<run-id>
```

Optional automatic triage:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visual-triage \
  --baseline out/.tmp/<run-id>/output.drawio-preview.png \
  --candidate out/.tmp/<run-id>/output.visio-preview.png \
  --mode stage2-vsdx \
  --report out/.tmp/<run-id>/output.stage2-triage.json \
  --diff out/.tmp/<run-id>/output.stage2-diff.ppm
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
- Final `.drawio` is in `out/`, if generated or repaired, and was validated after its last modification.
- Final `.vsdx` is in `out/`, if exported, and was validated after its last modification.
- `.drawio` preview PNGs, Visio COM preview PNGs, worklists, source baselines, reports, and diffs were written under `out/.tmp/<run-id>/` during validation.
- For multi-page inputs, every mapped page had a source baseline during validation when available; every mapped page had draw.io and Visio preview evidence in scratch, or a clearly reported reason for omission.
- The conversion worklist existed in scratch during validation and its required checks were complete or explicitly marked unavailable before cleanup.
- `audit-drawio` passed, or the file is clearly marked as a risk build.
- `validate-vsdx` passed.
- draw.io Desktop version used was `26.0.16`.
- On success, `scratch-clean` removed `out/.tmp/<run-id>` and `final-clean out --stem <stem> --deliverables-only --apply` removed root-level non-deliverable files from `out/`. On failure, scratch was retained and reported.

Final cleanup commands, only after all required validation gates pass:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py scratch-clean out/.tmp/<run-id>
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py final-clean out --stem <stem> --deliverables-only --apply
```

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
2. Audit the original file and follow the existing-file repair loop in `references/drawio-generation.md`.
3. Preserve layout, layer structure, colors, title hierarchy, badges, card sizing, section color strips, and overall proportions; do not add new arrows, flow lines, relationship labels, or structural elements unless the source diagram already has them or the user asks for them.
4. Export the original `.drawio` preview and compare the optimized preview against it.
5. Export and validate VSDX only after the Source-to-Draw.io Preview Gate passes.
6. Compare the Visio-rendered preview against the Stage 1-approved optimized `.drawio` preview.

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

Gate: normalize VSDX color cells after export and before final validation. The detailed rule belongs to `references/vsdx-export.md`.

### TextXForm

If a shape's selection box is correct but its text renders offset in Visio, check the VSDX `TextXForm`, not only the draw.io geometry.

Gate: normalize `TextXForm` only for appropriate text shapes, then export a Visio COM PNG preview and compare it with the `.drawio` preview. The detailed rule and exclusions belong to `references/vsdx-export.md`.

## 6. Command Reference

Ensure draw.io Desktop `26.0.16`:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure
```

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
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py repair-drawio input.drawio -o out/.tmp/<run-id>/input.repaired1.drawio
```

Export `.drawio` preview:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000 --out-dir out/.tmp/<run-id>
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview-pages input.drawio --width 2000 --out-dir out/.tmp/<run-id>
```

Generate/update a conversion worklist:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py worklist source.html --drawio out/source.drawio --out-dir out/.tmp/<run-id>
```

Export VSDX:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio -o out/<stem>.vsdx
```

Stage 2 round-trip artifact generation:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output-name --width 2000 --evidence-dir out/.tmp/<run-id>
```

Export all Visio-rendered page previews for a multi-page VSDX:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py visio-preview-pages out/output.vsdx --stem output-name --out-dir out/.tmp/<run-id>
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
  --report out/.tmp/<run-id>/visual.json \
  --diff out/.tmp/<run-id>/visual-diff.ppm
```

Audit important text:

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py audit-text output.vsdx --text "Important Heading"
```

## 7. Common Failure Handling

### `audit-drawio` Fails

- Treat this as a source-side gate failure.
- Follow `references/drawio-generation.md` for new-diagram source fixes, existing-diagram repair, and unresolved blockers.
- Do not call a risky export final. Use `--allow-risky` only for an explicitly labeled risk build.

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

- Treat this as a source text-structure failure.
- Follow `references/drawio-generation.md` for source fixes and `references/vsdx-export.md` for VSDX verification.

### Text Is Offset in Visio

- Treat this as a VSDX `TextXForm` gate failure.
- Follow `references/vsdx-export.md` for normalization details and exclusions.

## 8. Useful References

- `references/drawio-generation.md`: detailed `.drawio` generation, repair, image rebuild, HTML conversion, source contract, and Stage 1 mapping guidance.
- `references/vsdx-export.md`: detailed draw.io Desktop `26.0.16` setup, preview/export, VSDX validation, color normalization, `TextXForm`, Visio COM preview, text weight, and Stage 2 guidance.

## 9. Final Response

Report only useful artifacts:

- final `.drawio` source path, if generated or changed
- final `.vsdx` path, if exported
- validation summary, including whether Visio COM preview validation completed
- scratch evidence path only when the run failed or the user asked to retain audit evidence
- draw.io CLI/Desktop version used
- short validation result
