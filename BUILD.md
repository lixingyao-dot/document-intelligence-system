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

**界面像没更新？**  
1. 必须运行**本次**产物：`dist-electron\win-unpacked\文档智能系统.exe`（不要点开始菜单里旧安装包的快捷方式）。  
2. 设置里查看「界面 v… · 构建 …」时间，应与刚跑完 `build.ps1` 的时间一致。  
3. 开发时若开着 `run_dev.ps1` 或 8766 端口的 API，先关掉再启动打包版。  
4. 勿只跑 `npm run build:electron`；那会复用旧的 `dist-api`。

**毛玻璃不明显？**  
Windows 11 上 Electron 会尝试 `acrylic` 窗口材质；Win10 主要依赖 CSS `backdrop-filter`，观感会弱一些。

**工作流组件库自检（无需前端）**  

```powershell
# 快速自检（无需 Key）
python scripts\test_workflow_components.py

# 小米 MiMo 真实 API（Key 勿提交仓库）
$env:MIMO_API_KEY = "你的-token"
$env:MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
$env:MIMO_MODEL = "mimo-v2.5-pro"
python scripts\test_workflow_components.py --live
```

也可复制 `scripts/mimo.env.example` → `scripts/mimo.local.env` 填入后执行 `--live`。模型名须**小写**（如 `mimo-v2.5-pro`、`mimo-v2.5`）。
