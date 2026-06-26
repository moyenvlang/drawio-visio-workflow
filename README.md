# Draw.io Visio Workflow Skill

这是一个用于将图片、`.drawio`、HTML 格式的流程图或架构图高保真转换为 Visio `.vsdx` 文件的 Codex Skill。

它的核心目标是：解决好看的流程图、框架图、架构图在导出到 Visio 后难以高度还原的问题。它会把图片、已有 `.drawio` 或 HTML 中的图转换/重建为适合 VSDX 导出的 `.drawio` 源文件；先导出预览图确认效果，再使用 draw.io Desktop `26.0.16` 导出真正可用的 Microsoft Visio `.vsdx` 文件，并对导出结果做结构和视觉校验。

## 适用场景

- 图片转 VSDX：根据截图、图片或视觉参考重建可编辑的 `.drawio` 流程图，再导出为高保真的 `.vsdx`。
- `.drawio` 转 VSDX：优化已有 `.drawio`，减少导出后字体、加粗、颜色、圆角、换行、布局、文字位置等偏差。
- HTML 转 VSDX：从 HTML 中提取或转换 draw.io 图数据，生成更适合 VSDX 导出的 `.drawio` 文件，再导出为 `.vsdx`。
- 高保真还原：尽量保持原图的布局、配色、标题层级、卡片结构、徽章、文字样式和整体观感。
- 导出与校验：使用 draw.io Desktop `26.0.16` 导出真正的 Visio `.vsdx`，并通过预览图和结构校验确认结果。

## 核心流程

1. 从图片、`.drawio` 或 HTML 转换/重建 VSDX-friendly `.drawio` 文件。
2. 导出 PNG 预览图，确认 draw.io 中的视觉效果。
3. 使用 draw.io Desktop `26.0.16` 导出 VSDX。
4. 校验 VSDX 是否是真正的 Visio ZIP 包。
5. 将 VSDX 再渲染成 PNG，与 `.drawio` 预览图进行对比。
6. 对关键文本做加粗、颜色等样式检查。

## 关键规则

- `.drawio` 是唯一可编辑源文件。
- 原始 `.drawio` 文件保留在原位置。
- 转换或修复后的 `.drawio` 文件放入原文件同级的 `out/` 文件夹。
- 导出的 `.vsdx` 文件和截图/预览图片也放入 `out/` 文件夹。
- 临时文件、中间失败修复文件、对比页、解包目录等用完后删除，不保留。
- VSDX 导出必须使用 draw.io Desktop `26.0.16`。
- 不使用 draw.io `30.x` CLI 作为最终 VSDX 导出工具。
- 对需要在 Visio 中保持加粗、换行、白色文字等效果的文本，尽量拆成独立 `mxCell`，避免依赖复杂 HTML 标签。
- VSDX 导出后会对颜色单元做归一化：保留 `V="#RRGGBB"`，并补充 `F="RGB(r,g,b)"`。
- 对标题/标签文字在 Visio 中出现“选框位置正确但文字显示偏移”的情况，按 TextXForm 规则修正文本块锚点，并重新渲染预览图对比。

## 包含内容

```text
drawio-visio-workflow/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── drawio-generation.md
│   └── vsdx-export.md
└── scripts/
    ├── drawio_cli.py
    └── drawio_codec.py
```

## 安装方式

将本仓库克隆到 Codex skills 目录：

```bash
git clone https://github.com/moyenvlang/drawio-visio-workflow.git ~/.codex/skills/drawio-visio-workflow
```

然后在 Codex 中提出与 draw.io、流程图、架构图、VSDX 导出相关的任务即可触发使用。

## 常用脚本

检查或安装 draw.io Desktop `26.0.16`：

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py ensure
```

生成 `.drawio` 预览图：

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py preview input.drawio --width 2000
```

导出并校验 VSDX：

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py export-vsdx input.drawio
```

执行完整的 VSDX 往返校验：

```bash
python3 ~/.codex/skills/drawio-visio-workflow/scripts/drawio_cli.py roundtrip-check input.drawio --stem output-name --width 2000
```

## 输出约定

假设原文件为：

```text
project/diagram.drawio
```

最终交付文件会放在：

```text
project/out/
├── diagram.repaired.drawio
├── diagram.vsdx
├── diagram.drawio-preview.png
└── diagram.vsdx-preview.png
```

原始文件仍保留在：

```text
project/diagram.drawio
```

## 注意事项

这个仓库的 README 用于 GitHub 展示说明；真正供 Codex 加载和执行的 skill 入口是 `SKILL.md`。

如果只验证 VSDX 是否是 ZIP 包，仍然可能漏掉字体、加粗、颜色、换行等视觉问题。因此本 skill 要求导出后再渲染 VSDX 预览图，并与 `.drawio` 预览图进行对比。
