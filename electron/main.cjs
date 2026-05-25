/**
 * Electron 主进程：拉起本地 Python API，在 BrowserWindow 中加载同一套 Vue 前端。
 */
const { app, BrowserWindow, dialog, shell, Menu, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')
const fsp = fs.promises
const http = require('http')
const { spawn } = require('child_process')

const APP_TITLE = '文档智能系统'
const DEFAULT_PORT = 8766

let mainWindow = null
let backendProc = null
let apiPort = DEFAULT_PORT
let lastSaveDialogDir = ''

function lastSaveDirConfigPath() {
  return path.join(app.getPath('userData'), 'last-save-dialog-dir.json')
}

function loadLastSaveDialogDir() {
  try {
    const raw = fs.readFileSync(lastSaveDirConfigPath(), 'utf8')
    const parsed = JSON.parse(raw)
    const dir = String(parsed?.dir || '').trim()
    if (dir && fs.existsSync(dir)) {
      lastSaveDialogDir = dir
    }
  } catch {
    /* ignore */
  }
}

function persistLastSaveDialogDir(dirPath) {
  const dir = path.dirname(dirPath)
  if (!dir) return
  lastSaveDialogDir = dir
  try {
    fs.writeFileSync(lastSaveDirConfigPath(), JSON.stringify({ dir }), 'utf8')
  } catch {
    /* ignore */
  }
}

function saveDialogFilters(defaultName) {
  const ext = path.extname(String(defaultName || '')).toLowerCase()
  const map = {
    '.docx': { name: 'Word 文档', extensions: ['docx'] },
    '.doc': { name: 'Word 文档', extensions: ['doc'] },
    '.xlsx': { name: 'Excel 工作簿', extensions: ['xlsx'] },
    '.xls': { name: 'Excel 工作簿', extensions: ['xls'] },
    '.json': { name: 'JSON', extensions: ['json'] },
    '.pdf': { name: 'PDF', extensions: ['pdf'] },
    '.md': { name: 'Markdown', extensions: ['md'] },
    '.txt': { name: '文本', extensions: ['txt'] },
  }
  const spec = map[ext]
  if (!spec) return [{ name: '所有文件', extensions: ['*'] }]
  return [spec, { name: '所有文件', extensions: ['*'] }]
}

function appRoot() {
  return path.resolve(__dirname, '..')
}

function userDataDir() {
  return path.join(app.getPath('userData'), 'data')
}

function packagedBackendExe() {
  return path.join(
    process.resourcesPath,
    'backend',
    'DocumentIntelligenceApi',
    'DocumentIntelligenceApi.exe',
  )
}

function resolvePython() {
  const fromEnv = process.env.DOC_INTEL_PYTHON
  if (fromEnv && fs.existsSync(fromEnv)) return fromEnv
  return process.platform === 'win32' ? 'python' : 'python3'
}

function killBackend() {
  const proc = backendProc
  backendProc = null
  if (!proc || proc.killed) return
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t'], {
        windowsHide: true,
        stdio: 'ignore',
      })
    } else {
      proc.kill('SIGTERM')
    }
  } catch {
    try {
      proc.kill()
    } catch {
      /* ignore */
    }
  }
}

function spawnBackend(port) {
  const env = {
    ...process.env,
    DOC_INTEL_DATA_DIR: userDataDir(),
    DOC_INTEL_DESKTOP: '1',
    DOC_INTEL_ELECTRON: '1',
    DESKTOP_API_PORT: String(port),
    PYTHONIOENCODING: 'utf-8',
  }

  const exe = packagedBackendExe()
  if (app.isPackaged && fs.existsSync(exe)) {
    backendProc = spawn(exe, ['--headless', '--port', String(port)], {
      env,
      cwd: path.dirname(exe),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  } else {
    const serverEntry = path.join(appRoot(), 'server_entry.py')
    if (!fs.existsSync(serverEntry)) {
      throw new Error(`未找到后端启动脚本: ${serverEntry}`)
    }
    backendProc = spawn(resolvePython(), [serverEntry, '--port', String(port)], {
      env,
      cwd: appRoot(),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  }

  backendProc.on('error', (err) => {
    console.error('[backend spawn]', err)
  })

  const logChunk = (label, chunk) => {
    const text = chunk.toString().trim()
    if (text) console.log(`[backend ${label}]`, text)
  }
  backendProc.stdout?.on('data', (c) => logChunk('out', c))
  backendProc.stderr?.on('data', (c) => logChunk('err', c))
  backendProc.on('exit', (code, signal) => {
    if (code != null && code !== 0) {
      console.error(`[backend] exited code=${code} signal=${signal}`)
    }
    backendProc = null
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.close()
    }
  })
}

function waitHealth(port, timeoutMs = 90000) {
  const url = `http://127.0.0.1:${port}/health`
  const started = Date.now()

  return new Promise((resolve) => {
    const tick = () => {
      const req = http.get(url, { timeout: 2000 }, (res) => {
        res.resume()
        if (res.statusCode === 200) {
          resolve(true)
          return
        }
        retry()
      })
      req.on('error', retry)
      req.on('timeout', () => {
        req.destroy()
        retry()
      })

      function retry() {
        if (Date.now() - started >= timeoutMs) {
          resolve(false)
          return
        }
        setTimeout(tick, 400)
      }
    }
    tick()
  })
}

function registerWindowIpc() {
  ipcMain.handle('window:minimize', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.minimize()
  })
  ipcMain.handle('window:maximize', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return false
    if (mainWindow.isMaximized()) mainWindow.unmaximize()
    else mainWindow.maximize()
    return mainWindow.isMaximized()
  })
  ipcMain.handle('window:close', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close()
  })
  ipcMain.handle('window:isMaximized', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return false
    return mainWindow.isMaximized()
  })
  ipcMain.handle('dialog:pickDirectory', async () => {
    if (!mainWindow || mainWindow.isDestroyed()) return null
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '选择输出文件夹',
      properties: ['openDirectory', 'createDirectory'],
    })
    if (result.canceled || !result.filePaths?.length) return null
    return result.filePaths[0]
  })
  ipcMain.handle('dialog:saveFileFromBuffer', async (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return { ok: false, canceled: true, error: 'window_unavailable' }
    }
    const defaultName = path.basename(String(payload?.defaultName || 'download').trim() || 'download')
    const base64 = String(payload?.base64 || '')
    if (!base64) {
      return { ok: false, canceled: false, error: 'empty_buffer' }
    }
    const defaultPath = lastSaveDialogDir
      ? path.join(lastSaveDialogDir, defaultName)
      : defaultName
    const result = await dialog.showSaveDialog(mainWindow, {
      title: '另存为',
      defaultPath,
      filters: saveDialogFilters(defaultName),
    })
    if (result.canceled || !result.filePath) {
      return { ok: false, canceled: true }
    }
    const destPath = path.resolve(result.filePath)
    try {
      await fsp.writeFile(destPath, Buffer.from(base64, 'base64'))
      persistLastSaveDialogDir(destPath)
      return { ok: true, savedPath: destPath }
    } catch (err) {
      return { ok: false, canceled: false, error: String(err?.message || err) }
    }
  })
  ipcMain.handle('dialog:saveFile', async (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return { ok: false, canceled: true, error: 'window_unavailable' }
    }
    const sourcePath = path.resolve(String(payload?.sourcePath || '').trim())
    const defaultName = path.basename(String(payload?.defaultName || '').trim() || sourcePath)
    if (!sourcePath || !fs.existsSync(sourcePath) || !fs.statSync(sourcePath).isFile()) {
      return { ok: false, canceled: false, error: 'source_not_found' }
    }
    const defaultPath = lastSaveDialogDir
      ? path.join(lastSaveDialogDir, defaultName)
      : defaultName
    const result = await dialog.showSaveDialog(mainWindow, {
      title: '另存为',
      defaultPath,
      filters: saveDialogFilters(defaultName),
    })
    if (result.canceled || !result.filePath) {
      return { ok: false, canceled: true }
    }
    const destPath = path.resolve(result.filePath)
    try {
      await fsp.copyFile(sourcePath, destPath)
      persistLastSaveDialogDir(destPath)
      return { ok: true, savedPath: destPath }
    } catch (err) {
      return { ok: false, canceled: false, error: String(err?.message || err) }
    }
  })
  ipcMain.handle('shell:openPath', async (_event, targetPath) => {
    const p = String(targetPath || '').trim()
    if (!p) return ''
    return shell.openPath(p)
  })
}

function notifyMaximizeState() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents.send('window:maximized-changed', mainWindow.isMaximized())
}

function createWindow(url) {
  const iconPath = path.join(appRoot(), 'assets', 'app-icon.ico')
  const winOpts = {
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: APP_TITLE,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  }
  if (fs.existsSync(iconPath)) {
    winOpts.icon = iconPath
  }

  mainWindow = new BrowserWindow(winOpts)
  if (process.platform === 'win32' && typeof mainWindow.setBackgroundMaterial === 'function') {
    try {
      mainWindow.setBackgroundMaterial('acrylic')
    } catch {
      /* Win10 或未启用时忽略 */
    }
  }
  mainWindow.setMenuBarVisibility(false)
  mainWindow.removeMenu()
  mainWindow.on('maximize', notifyMaximizeState)
  mainWindow.on('unmaximize', notifyMaximizeState)
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.loadURL(url)

  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith('http://') || target.startsWith('https://')) {
      shell.openExternal(target)
    }
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

async function boot() {
  const requested = parseInt(process.env.DESKTOP_API_PORT || String(DEFAULT_PORT), 10)
  apiPort = Number.isFinite(requested) && requested > 0 ? requested : DEFAULT_PORT

  try {
    spawnBackend(apiPort)
  } catch (err) {
    dialog.showErrorBox(APP_TITLE, `无法启动本地服务：${err.message}`)
    app.quit()
    return
  }

  const ok = await waitHealth(apiPort)
  if (!ok) {
    killBackend()
    dialog.showErrorBox(
      APP_TITLE,
      '本地 API 启动超时。\n\n请在本目录执行 scripts\\run_dev.ps1 或重新运行 scripts\\build.ps1 打包。',
    )
    app.quit()
    return
  }

  createWindow(`http://127.0.0.1:${apiPort}/`)
}

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })

  app.whenReady().then(() => {
    Menu.setApplicationMenu(null)
    loadLastSaveDialogDir()
    registerWindowIpc()
    return boot()
  })

  app.on('window-all-closed', () => {
    killBackend()
    if (process.platform !== 'darwin') app.quit()
  })

  app.on('before-quit', () => {
    killBackend()
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0 && backendProc) {
      createWindow(`http://127.0.0.1:${apiPort}/`)
    }
  })
}
