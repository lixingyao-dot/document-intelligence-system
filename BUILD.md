# 自包含构建指南（desktop-electron）

本目录是**独立发行版**：前端、后端 API、Electron 壳、业务代码 `src/` 均在此文件夹内协作，**不依赖**同仓库的 `desktop-local/`、`extended-frontend/` 或 Web 前端。

界面风格为 **Electron 毛玻璃**（`electron-glass` / `glass-deep`），与 `desktop-local` 的白底像素风（`pixel-paper`）已分叉。

---

## 目录内关系（端到端）

```
frontend/dist  ──PyInstaller──►  dist-api/DocumentIntelligenceApi.exe
                                        │
                                        └──extraResources──►  dist-electron/（安装包）
electron/main.cjs  ──启动──►  上述 API  ──HTTP──►  加载内嵌的 frontend/dist
```

| 步骤 | 命令 / 产物 |
|------|-------------|
| 开发 | `.\scripts\run_dev.ps1` → Electron + 本目录 `server_entry.py` |
| 完整打包 | `.\scripts\build.ps1` 或 `npm run build` |
| 仅 API | `.\scripts\build_api.ps1` 或 `npm run build:api` |
| 运行 | `dist-electron\win-unpacked\文档智能系统.exe` |

---

## 一键从头到尾构建

在 **desktop-electron** 根目录执行：

```powershell
.\scripts\build.ps1
```

等价于 `npm run build`。脚本会依次：

1. 构建 `frontend/dist`（毛玻璃 Vue）
2. 校验 `electron-glass` + `glass-deep`（拒绝 `pixel-paper`）
3. PyInstaller 打包 API，**内嵌**当前 `frontend/dist`
4. 再次校验 API 包内前端与源码时间戳
5. `electron-builder` 生成 `dist-electron/`

可选参数：

- `-SkipApi`：跳过 API 重建（仅当包内前端已是最新毛玻璃版）
- `-SkipElectron`：只打到 `dist-api`，不生成安装包

---

## 环境要求

- Windows 10/11 x64
- Node.js 18+、npm
- Python 3.11+（构建 API 时由 `.venv-build` 隔离）

---

## 与仓库其它目录

| 操作 | 说明 |
|------|------|
| 日常开发 / 打包 | **只需本目录**，不必打开 `desktop-local` |
| `.\scripts\sync_src.ps1` | **可选**：从仓库根 `src/` 同步业务代码到本目录 `src/` |

---

## 常见问题

**打包后仍是白底像素风？**  
说明 `dist-api` 里仍是旧前端。请执行完整 `.\scripts\build.ps1`（不要只跑 `npm run build:electron`），并关闭本目录下旧的 `DocumentIntelligenceApi` 进程后再启动 `文档智能系统.exe`。

**毛玻璃不明显？**  
Windows 11 上 Electron 会尝试 `acrylic` 窗口材质；Win10 主要依赖 CSS `backdrop-filter`，观感会弱一些。
