# Draw.io Visio Workflow Skill

这是一个用于绘制流程图、架构图并导出 Visio `.vsdx` 文件的 Codex Skill。

它的核心目标是：根据需求生成 `.drawio` 源文件，先导出预览图确认效果，再使用 draw.io Desktop `26.0.16` 导出真正可用的 Microsoft Visio `.vsdx` 文件，并对导出结果做结构和视觉校验。

## 适用场景

- 根据文字需求绘制流程图、框架图、逻辑架构图、系统关系图。
- 将已有 `.drawio` 文件优化为更适合导出 VSDX 的结构。
- 生成 `.drawio` 预览图，确认视觉效果后再导出 `.vsdx`。
- 排查 draw.io 转 VSDX 后的字体、加粗、颜色、布局、圆角、文本换行等问题。
- 避免 draw.io 新版本 CLI 生成“扩展名是 `.vsdx`、内容实际是 PDF”的无效文件。

## 核心流程

1. 生成或修复 `.drawio` 文件。
2. 导出 PNG 预览图，确认 draw.io 中的视觉效果。
3. 使用 draw.io Desktop `26.0.16` 导出 VSDX。
4. 校验 VSDX 是否是真正的 Visio ZIP 包。
5. 将 VSDX 再渲染成 PNG，与 `.drawio` 预览图进行对比。
6. 对关键文本做加粗、颜色等样式检查。

## 关键规则

- `.drawio` 是唯一可编辑源文件。
- 过程文件放在原 `.drawio` 同级目录下的 `temp/` 文件夹。
- 最终 `.drawio` 和 `.vsdx` 放在原文件同级目录。
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

最终文件会放在：

```text
project/diagram.vsdx
```

过程文件会放在：

```text
project/temp/
├── diagram.preview.png
├── output-name.drawio-preview.png
├── output-name.vsdx-preview.png
└── output-name.compare.html
```

## 注意事项

这个仓库的 README 用于 GitHub 展示说明；真正供 Codex 加载和执行的 skill 入口是 `SKILL.md`。

如果只验证 VSDX 是否是 ZIP 包，仍然可能漏掉字体、加粗、颜色、换行等视觉问题。因此本 skill 要求导出后再渲染 VSDX 预览图，并与 `.drawio` 预览图进行对比。
