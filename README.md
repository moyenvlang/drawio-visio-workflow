# Draw.io Visio Workflow Skill

这是一个用于绘制流程图、架构图并导出 Visio `.vsdx` 文件的 Codex Skill。

它的核心目标是：支持从需求描述生成 `.drawio`、优化已有 `.drawio`、或从 HTML 提取/转换 draw.io 图数据，统一生成适合 VSDX 导出的 `.drawio` 源文件；先导出预览图确认效果，再使用 draw.io Desktop `26.0.16` 导出真正可用的 Microsoft Visio `.vsdx` 文件，并对导出结果做结构和视觉校验。

## 适用场景

- 从 0 到 1 绘制图：根据需求描述生成流程图、框架图、逻辑架构图、系统关系图等 `.drawio` 文件，并生成预览图确认效果。
- 优化已有 `.drawio`：将现有 `.drawio` 文件调整为更适合导出 VSDX 的结构，减少导出后字体、加粗、颜色、圆角、换行、布局等偏差。
- 从 HTML 转换：从 HTML 中提取或转换 draw.io 图数据，生成更适合 VSDX 导出的 `.drawio` 文件，再导出为 `.vsdx`。
- 导出与校验 VSDX：使用 draw.io Desktop `26.0.16` 导出真正的 Visio `.vsdx`，避免生成 PDF 内容伪装成 `.vsdx`。
- 视觉回归检查：将 `.drawio` 和导出的 `.vsdx` 分别渲染为预览图，对比确认最终交付效果。

## 核心流程

1. 生成或修复 `.drawio` 文件。
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
