# Draw.io Visio Workflow Skill

把流程图、架构图、系统图更可靠地交付成可编辑的 Microsoft Visio `.vsdx` 文件。

这个 Codex Skill 面向经常需要在 draw.io、HTML 图表、截图和 Visio 之间转换图件的人：售前、咨询顾问、产品经理、架构师、工程团队、文档交付团队，以及需要把方案图纳入正式文档、投标材料或客户交付物的团队。

## 它解决什么问题

很多图在网页、PPT、截图或 draw.io 里看起来很好，但一到 Visio 里就会出现：

- 字体变形、中文换行异常
- 加粗、白字、颜色、圆角丢失
- 卡片、泳道、分层结构错位
- 只能交付图片，客户无法继续编辑
- 手工重画成本高，且版本越改越不稳定

这个 Skill 的目标是把这些图转换成更适合 Visio 使用的可编辑文件，减少重复手工修图，让最终交付更稳定。

## 能带来什么价值

- 将截图、HTML 图、draw.io 图转成可继续编辑的 Visio 文件
- 保留架构图常见的层级、卡片、分组、标签和说明区域
- 降低 draw.io 导出 Visio 后的字体、颜色、换行和位置偏差
- 让交付目录更干净：成功后只保留最终 `.drawio` 和 `.vsdx`
- 适合批量整理方案图、架构图、系统图和技术文档图件

## 适合谁用

- 需要向客户交付 Visio 源文件的售前和咨询团队
- 需要维护系统架构图、数据架构图、技术路线图的架构师
- 需要把 HTML/网页图表整理成正式交付物的文档团队
- 需要从截图或旧图中重建可编辑图件的项目团队
- 使用 Codex 处理技术文档、图件转换和交付材料的开发者

## 支持的输入

- `.drawio` 文件
- HTML 中的图表或架构图
- 图片、截图、视觉参考
- 新建图件需求描述

## 输出结果

成功转换后，交付目录只保留最终文件：

```text
out/
├── <name>.drawio
└── <name>.vsdx
```

`.drawio` 是可编辑源文件，`.vsdx` 是最终 Visio 交付文件。

## 安装

克隆到 Codex skills 目录：

```bash
git clone https://github.com/moyenvlang/drawio-visio-workflow.git ~/.codex/skills/drawio-visio-workflow
```

然后在 Codex 中提出类似任务：

```text
把这个 HTML 架构图转成 VSDX
```

```text
把这张系统架构图截图重建成可编辑 Visio 文件
```

```text
优化这个 draw.io 文件并导出高保真 VSDX
```

## 环境要求

- Codex
- draw.io Desktop `26.0.16`
- 如需真实 Visio 效果校验：Windows + Microsoft Visio Desktop

Skill 会在执行时检查依赖，并在缺少必要组件时给出处理建议。

## 说明

这个 README 只介绍用途、价值和安装方式。详细执行流程、校验策略和内部约束由 Codex 读取 `SKILL.md` 和 `references/` 中的说明完成。
