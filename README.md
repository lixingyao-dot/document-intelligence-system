# 文档智能系统 · Electron 桌面版

基于大语言模型的**文档理解**与**多源数据融合**一体化桌面应用。本目录为可独立开发、打包的 Electron 发行版（前端 + 本地 API + 业务代码 `src/`）。

---

## 项目背景与目标

企业日常办公中积累了大量**非结构化文本**（合同、经营报告、客户反馈、技术资料等），格式不一、来源分散。传统人工阅读、摘录、录入效率低、易出错。

本系统以大语言模型（LLM）为核心，面向办公场景实现：

- 对多源异构文档的**自动理解、抽取与结构化**；
- 将非结构化信息转化为可关联、可分析的数据资产；
- 支撑**自动填表、智能问答、知识整理、跨文档检索**等应用。

程序可部署于**桌面端**（亦可扩展 Web / 服务端），通过本地 API 与前端协作完成文档处理任务。

---

## 核心能力与模块

| 能力模块 | 本桌面版实现 |
|----------|-------------|
| **文档智能操作**（自然语言编辑、格式调整、内容提取） | **智能对话**：文档理解、文档编辑（Agent A）；工作流中的摘要、润色、格式转换等 AI 节点 |
| **非结构化信息抽取** | **实体提取**（Agent B）：从 docx/pdf/txt/md 等抽取 JSON，可配合 Excel 模板 |
| **表格数据填写** | **表格填表**（Agent D）：数据源 Excel + Word/Excel 模板；支持「模板优先」填表与混合模式 |
| **多源数据融合与输出** | **文档库**管理多份源文件；**工作流**串联输入 → AI 处理 → 输出（PDF/MD/入库）；对话与工作流结果支持**另存为**到本地 |
| **桌面部署** | Electron 安装包（`Setup.exe`）或 `win-unpacked` 免安装目录；设置页配置多厂商 LLM Key |

### 智能体分工

| 智能体 | 职责 | 支持格式（典型） |
|--------|------|------------------|
| **Agent A** | 文档理解、按自然语言编辑文档 | docx、txt、md、xlsx 等 |
| **Agent B** | 非结构化文档实体/字段抽取 → JSON | docx、pdf、txt、md |
| **Agent D** | Excel 筛选 + 填入 Word/Excel 模板 | xlsx 数据源 + xlsx/docx 模板 |

桌面版由 **A / B / D 三类智能体**协作；会话、文档库、工作流与配置均使用**本地 JSON + 文件**，无需数据库即可完整使用。

---

## 主要功能一览

- **文档库**：上传与管理 PDF / Word / Excel / Markdown / 文本等文档。  
- **智能对话**：默认对话、文档理解、文档编辑、混合模式（理解 + 填表/提取）。  
- **工作流**：可视化编排（文档输入 → AI 翻译/摘要/抽取等 → 文档输出）；内置「文档翻译流」「内容提取流」等示例。  
- **模型设置**：应用内配置 DeepSeek / 智谱 / OpenAI 兼容等 API，Key 按供应商独立保存。  
- **结果保存**：生成文件通过系统**另存为**对话框保存（不强制写入固定目录、不自动塞入文档库）。

手工测试样例见：[test-fixtures/templates/README.md](test-fixtures/templates/README.md)。

### 生成项目展示 PPT（含实测截图）

将界面截图放入 `output/presentation_assets/`（`img01.png` … `img14.png`），然后执行：

```powershell
cd desktop-electron
python scripts\build_presentation_with_screenshots.py
```

产物：`output/文档智能系统_项目展示_v2.pptx`（9 页：含三类智能体专页，无数据库/Agent C）。

---

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│  Electron 壳（electron/main.cjs · preload.cjs）          │
│  · 自定义标题栏 · 本地「另存为」· 启动/托管后端进程       │
└──────────────────────────┬──────────────────────────────┘
                           │ load UI
┌──────────────────────────▼──────────────────────────────┐
│  Vue 3 前端（frontend/）                                 │
│  文档库 · 智能对话 · 工作流画布 · 设置                   │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼──────────────────────────────┐
│  FastAPI 本地服务（开发：server_entry.py；发行：          │
│  DocumentIntelligenceApi.exe）                          │
│  api/ · service/ · core/orchestrator/ · core/agents/    │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  数据与产物                                              │
│  %APPDATA%\document-intelligence-desktop-electron\data  │
│  （settings.json、本地文档库、工作流、会话等）            │
└─────────────────────────────────────────────────────────┘
```

| 能力 | 说明 |
|------|------|
| 界面 | Chromium + 自定义标题栏 |
| 后端 | `DocumentIntelligenceApi.exe`（PyInstaller）或开发时 `server_entry.py` |
| 业务代码 | `desktop-electron/src/`（可由仓库根 `src/` 同步） |
| 当前版本 | 见 `package.json` |

---

## 目录结构

```
desktop-electron/
  electron/           # 主进程、预加载脚本
  frontend/           # Vue 界面（Vite 构建）
  backend/            # 桌面专用路由（设置、本地文档库等）
  src/                # 核心业务（api、core、db、service…）
  scripts/            # run_dev、build、sync_src、build_api
  test-fixtures/      # 手工测试用模板与样例文档
  server_entry.py     # 开发态 API 入口
  requirements.txt    # Python 依赖
  assets/             # 应用图标等
  dist-api/           # PyInstaller 输出（构建后）
  dist-electron/      # 安装包与 win-unpacked（构建后）
```

本目录**可独立运行与打包**，不依赖仓库根的 `desktop-local/`；与根目录 `src/` 的关系见下文「与主线代码同步」。

---

## 快速开始

### 环境要求

- Windows 10/11（x64）  
- Node.js 18+、npm  
- Python 3.11+（仅开发或未打包 API 时需要）  
- 可访问的 LLM API（在应用「API 与模型设置」中配置）

### 开发运行

```powershell
cd desktop-electron
.\scripts\run_dev.ps1
```

或：`.\scripts\run_dev.cmd`

首次运行会自动构建 `frontend/dist`（若不存在），并设置 `DOC_INTEL_DESKTOP=1`、`DOC_INTEL_ELECTRON=1`。

### 打包安装程序

```powershell
cd desktop-electron
.\scripts\build.ps1 -RebuildApi
```

产物示例：

- 安装包：`dist-electron\文档智能系统 Setup <版本>.exe`  
- 免安装：`dist-electron\win-unpacked\文档智能系统.exe`

仅重建 API、跳过前端时可使用 `.\scripts\build_api.ps1`。

---

## 模型与数据配置

1. 启动应用 → **API 与模型设置**。  
2. 下拉选择供应商，分别填写 **API Key**、**模型名**、**Base URL**（若需要）。  
3. 配置文件路径：  
   `%APPDATA%\document-intelligence-desktop-electron\data\settings.json`

未配置或 Key 无效时，文档理解、翻译、抽取、填表等依赖 LLM 的功能将无法完成。

---

## 与主线代码同步

仓库根目录 `src/` 有更新时，可同步到本目录：

```powershell
cd desktop-electron
.\scripts\sync_src.ps1
```

同步会排除 `temp/`、`output/`、用户 `workspace/library` 等运行时数据。  
**Electron 相关改动请优先在本目录完成**；与 `desktop-local`（pywebview 版）前端已分叉。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [../README.md](../README.md) | 仓库总览（Web 后端、Docker、环境变量） |
| [test-fixtures/templates/README.md](test-fixtures/templates/README.md) | 桌面版手工测试文件与推荐组合 |
| [../docker/README.md](../docker/README.md) | 服务器 Docker 部署（非桌面版） |
