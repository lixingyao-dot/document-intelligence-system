# 文档智能系统 · Electron 桌面版

**完全独立目录**：Electron 壳 + Vue 前端 + 本地 API + 业务代码 `src/`，不依赖仓库根目录的 `desktop-local/` 或根级 `src/` 来运行/打包。

| 能力 | 说明 |
|------|------|
| 界面 | Chromium + 自定义标题栏 |
| 后端 | `DocumentIntelligenceApi.exe` 或开发时 `server_entry.py` |
| 业务代码 | `desktop-electron/src/`（api、core、db…） |
| 数据 | `%APPDATA%\document-intelligence-desktop-electron\data` |

## 目录结构

```
desktop-electron/
  electron/           # main.cjs、preload.cjs
  frontend/           # Vue 界面
  backend/            # 桌面壳、设置 API、本地文档库路由
  src/                # 核心业务（自仓库 src 同步而来）
  scripts/            # run_dev、build、sync_src
  server_entry.py
  requirements.txt    # Python 依赖（自包含）
  data/               # 示例 settings.json
  assets/
  workspace/          # 工作流模板（打包用，可选）
```

## 开发运行

```powershell
cd desktop-electron
.\scripts\run_dev.cmd
```

## 打包安装程序

```powershell
.\scripts\build.cmd
```

## 与仓库主线的 src 同步

开发时若主仓库 `src/` 有更新，可同步到本目录：

```powershell
.\scripts\sync_src.ps1
```

同步会排除 `temp/`、`output/`、用户 `workspace/library` 等运行时数据。

## 模型设置

应用内 **「API 与模型设置」** → 下拉选择供应商，分别保存 Key / 模型 / Base URL。

配置文件：`%APPDATA%\document-intelligence-desktop-electron\data\settings.json`

## 与 desktop-local（pywebview 版）

- **desktop-electron**：本目录，Electron 路线，自带 `src/`。
- **desktop-local**：pywebview 单 exe，仍使用仓库根 `src/`。

二者前端已分叉；改 Electron 请只改本目录。
