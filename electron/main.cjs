/**
 * Electron 主进程：拉起本地 Python API，在 BrowserWindow 中加载同一套 Vue 前端。
 */
const { app, BrowserWindow, dialog, shell, Menu, ipcMain, screen, desktopCapturer } = require('electron')
const path = require('path')
const fs = require('fs')
const fsp = fs.promises
const http = require('http')
const net = require('net')
const os = require('os')
const { spawn } = require('child_process')

if (process.platform === 'win32') {
  app.commandLine.appendSwitch('enable-features', 'WindowsSystemBackdropComposition')
}

/** Win11 构建号 >= 22000（os.release() 如 10.0.26200） */
function isWindows11OrLater() {
  if (process.platform !== 'win32') return false
  const build = parseInt(String(os.release()).split('.')[2] || '0', 10)
  return build >= 22000
}

/** Win11：DWM Acrylic 原生窗口级毛玻璃；Win10：桌面截图 + CSS blur 回退 */
function usesNativeWinAcrylic() {
  return process.platform === 'win32' && isWindows11OrLater()
}

function usesDesktopBackdropFallback() {
  return process.platform === 'win32' && !isWindows11OrLater()
}

function getGlassInfo() {
  if (process.platform === 'win32') {
    return {
      platform: 'win32',
      glassMode: usesNativeWinAcrylic() ? 'native-acrylic' : 'screenshot-fallback',
      isWindows11: isWindows11OrLater(),
      material: usesNativeWinAcrylic() ? 'acrylic' : 'none',
      nativeWindowControls: false,
      titleBarHeight: TITLE_BAR_HEIGHT,
    }
  }
  if (process.platform === 'darwin') {
    return { platform: 'darwin', glassMode: 'native-vibrancy', isWindows11: false, material: 'vibrancy' }
  }
  return { platform: process.platform, glassMode: 'none', isWindows11: false, material: 'none' }
}

const APP_TITLE = '文档智能系统'
const DEFAULT_PORT = 8766
const PORT_SCAN_END = 8776

let mainWindow = null
let backendProc = null
let apiPort = DEFAULT_PORT
let lastSaveDialogDir = ''
/** @type {{ win: import('electron').BrowserWindow, edge: string, startMouseX: number, startMouseY: number, startBounds: Electron.Rectangle } | null} */
let windowResizeSession = null
let backdropRefreshTimer = null
let backdropCaptureInFlight = false

const WINDOW_MIN_WIDTH = 900
const WINDOW_MIN_HEIGHT = 600
const TITLE_BAR_HEIGHT = 40
const WM_SYSCOMMAND = 0x0112
const SC_RESTORE = 0xf120
const SC_MAXIMIZE = 0xf030

function getTargetWindow(event) {
  try {
    if (event?.sender) {
      const fromSender = BrowserWindow.fromWebContents(event.sender)
      if (fromSender && !fromSender.isDestroyed()) return fromSender
    }
  } catch {
    /* ignore */
  }
  const focused = BrowserWindow.getFocusedWindow()
  if (focused && !focused.isDestroyed()) return focused
  return mainWindow && !mainWindow.isDestroyed() ? mainWindow : null
}

function applyWinTitleBarOverlay(win) {
  /* 使用自定义 — □ ×，不再启用 titleBarOverlay */
}

function getDefaultWindowBounds() {
  const work = screen.getPrimaryDisplay().workArea
  const width = 1280
  const height = 800
  return {
    x: Math.round(work.x + Math.max(0, (work.width - width) / 2)),
    y: Math.round(work.y + Math.max(0, (work.height - height) / 2)),
    width,
    height,
  }
}

function isBoundsNearWorkArea(win, bounds) {
  if (!win || win.isDestroyed() || !bounds) return false
  const work = screen.getDisplayMatching(bounds).workArea
  return bounds.width >= work.width - 4 && bounds.height >= work.height - 4
}

/** 最大化状态下 setBounds 常被忽略，先退出再强制写入 */
function forceWindowBounds(win, bounds) {
  if (!win || win.isDestroyed() || !bounds) return
  const target = {
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  }
  if (win.isMaximized()) {
    try {
      win.unmaximize()
    } catch {
      /* ignore */
    }
  }
  win.setBounds(target)
  const applied = win.getBounds()
  if (
    Math.abs(applied.width - target.width) > 2 ||
    Math.abs(applied.height - target.height) > 2
  ) {
    win.setResizable(true)
    try {
      win.unmaximize()
    } catch {
      /* ignore */
    }
    win.setBounds(target)
  }
  const stillWrong = win.getBounds()
  if (
    Math.abs(stillWrong.width - target.width) > 2 ||
    Math.abs(stillWrong.height - target.height) > 2
  ) {
    win.hide()
    try {
      win.unmaximize()
    } catch {
      /* ignore */
    }
    win.setBounds(target)
    win.show()
  }
  win.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
}

/** Win 透明无边框窗原生 maximize/unmaximize 不可靠，改用手动 setBounds */
let isWindowExpanded = false
/** @type {Electron.Rectangle | null} */
let boundsBeforeExpand = null
/** @type {Electron.Rectangle | null} */
let normalWindowBounds = null
let handlingMaximizeTransition = false

function useCustomWindowExpand() {
  return process.platform === 'win32'
}

function rememberNormalBounds(win) {
  if (!win || win.isDestroyed() || handlingMaximizeTransition) return
  if (isWindowExpanded) return
  if (win.isMaximized()) return
  normalWindowBounds = win.getBounds()
}

function pickBoundsBeforeExpand(win) {
  if (boundsBeforeExpand) return boundsBeforeExpand
  if (normalWindowBounds) return normalWindowBounds
  if (!win || win.isDestroyed()) return null
  return win.getBounds()
}

function readWindowMaximizedState(win) {
  if (!win || win.isDestroyed()) return false
  if (useCustomWindowExpand()) return isWindowExpanded
  return win.isMaximized()
}

function notifyMaximizeState() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents.send('window:maximized-changed', readWindowMaximizedState(mainWindow))
}

function applyCustomWindowExpand(win) {
  const base = pickBoundsBeforeExpand(win)
  if (!base) return false
  boundsBeforeExpand = base
  const work = screen.getDisplayMatching(boundsBeforeExpand).workArea
  win.setBounds({
    x: Math.round(work.x),
    y: Math.round(work.y),
    width: Math.round(work.width),
    height: Math.round(work.height),
  })
  isWindowExpanded = true
  return true
}

function applyCustomWindowRestore(win) {
  const restore = boundsBeforeExpand || normalWindowBounds || getDefaultWindowBounds()
  forceWindowBounds(win, restore)
  isWindowExpanded = false
  boundsBeforeExpand = null
  normalWindowBounds = restore
}

/** 系统标题栏点最大化：记录还原前的尺寸（勿 unmaximize，否则还原钮失效） */
function handleWin32MaximizeEvent(win) {
  if (!win || win.isDestroyed() || handlingMaximizeTransition) return
  handlingMaximizeTransition = true
  try {
    if (win.isMaximized()) {
      try {
        win.unmaximize()
      } catch {
        /* ignore */
      }
    }
    if (!isWindowExpanded) {
      if (!boundsBeforeExpand) {
        rememberNormalBounds(win)
        boundsBeforeExpand = pickBoundsBeforeExpand(win) || getDefaultWindowBounds()
      }
      applyCustomWindowExpand(win)
    }
    notifyMaximizeState()
    scheduleDesktopBackdropRefresh(win, true)
  } finally {
    handlingMaximizeTransition = false
  }
}

/** 系统标题栏点还原：原生 unmaximize 常无效，强制 setBounds 回窗口化尺寸 */
function handleWin32UnmaximizeEvent(win) {
  if (!win || win.isDestroyed() || handlingMaximizeTransition) return
  handlingMaximizeTransition = true
  try {
    applyCustomWindowRestore(win)
    notifyMaximizeState()
    scheduleDesktopBackdropRefresh(win, true)
  } finally {
    handlingMaximizeTransition = false
  }
}

function toggleWindowMaximize(win) {
  if (!win || win.isDestroyed()) return false

  if (useCustomWindowExpand()) {
    if (isWindowExpanded || win.isMaximized() || isBoundsNearWorkArea(win, win.getBounds())) {
      applyCustomWindowRestore(win)
    } else {
      rememberNormalBounds(win)
      boundsBeforeExpand = win.getBounds()
      applyCustomWindowExpand(win)
    }
    notifyMaximizeState()
    scheduleDesktopBackdropRefresh(win, true)
    return readWindowMaximizedState(win)
  }

  if (win.isMaximized()) win.unmaximize()
  else win.maximize()
  notifyMaximizeState()
  return win.isMaximized()
}

function resetWindowExpandState() {
  isWindowExpanded = false
  boundsBeforeExpand = null
  normalWindowBounds = null
  handlingMaximizeTransition = false
}

function readSysCommand(wParam) {
  if (!wParam || wParam.length < 4) return 0
  return wParam.readUInt32LE(0) & 0xfff0
}

/** 透明窗下原生 unmaximize 常无效；拦截标题栏还原/最大化系统命令 */
function setupWin32SysCommandHook(win) {
  if (process.platform !== 'win32' || !win || win.isDestroyed()) return
  if (typeof win.hookWindowMessage !== 'function') return
  try {
    win.hookWindowMessage(WM_SYSCOMMAND, (wParam) => {
      const cmd = readSysCommand(wParam)
      if (cmd === SC_RESTORE) {
        handleWin32UnmaximizeEvent(win)
      } else if (cmd === SC_MAXIMIZE && !readWindowMaximizedState(win)) {
        handleWin32MaximizeEvent(win)
      }
    })
  } catch (err) {
    console.warn('[window] hookWindowMessage failed:', err?.message || err)
  }
}

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

function isPortFree(port) {
  return new Promise((resolve) => {
    const srv = net.createServer()
    srv.once('error', () => resolve(false))
    srv.once('listening', () => {
      srv.close(() => resolve(true))
    })
    srv.listen(port, '127.0.0.1')
  })
}

async function pickApiPort() {
  for (let port = DEFAULT_PORT; port < PORT_SCAN_END; port += 1) {
    if (await isPortFree(port)) return port
  }
  return DEFAULT_PORT
}

/** 仅结束本目录 dist-api / dist-electron 下的 API，避免误杀其它桌面版进程 */
function stopLocalStaleApis() {
  if (process.platform !== 'win32') return
  const roots = [
    path.join(appRoot(), 'dist-api'),
    path.join(appRoot(), 'dist-electron'),
  ]
  if (app.isPackaged && process.resourcesPath) {
    roots.push(path.join(process.resourcesPath, 'backend'))
  }
  const rootNorms = roots.map((r) => path.resolve(r).toLowerCase())
  try {
    const out = require('child_process').execSync(
      'wmic process where "name=\'DocumentIntelligenceApi.exe\'" get ExecutablePath,ProcessId /format:csv',
      { encoding: 'utf8', windowsHide: true },
    )
    for (const line of out.split(/\r?\n/)) {
      const parts = line.split(',').map((s) => s.trim()).filter(Boolean)
      if (parts.length < 2) continue
      const pid = parseInt(parts[parts.length - 1], 10)
      const exePath = parts.slice(0, -1).join(',').toLowerCase()
      if (!Number.isFinite(pid) || !exePath.endsWith('.exe')) continue
      const hit = rootNorms.some((root) => exePath.startsWith(root))
      if (hit) {
        try {
          spawn('taskkill', ['/pid', String(pid), '/f', '/t'], {
            windowsHide: true,
            stdio: 'ignore',
          })
        } catch {
          /* ignore */
        }
      }
    }
  } catch {
    /* ignore */
  }
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

function httpGet(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      const chunks = []
      res.on('data', (c) => chunks.push(c))
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          body: Buffer.concat(chunks).toString('utf8'),
        })
      })
    })
    req.on('error', reject)
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('timeout'))
    })
  })
}

async function waitHealth(port, timeoutMs = 90000) {
  const url = `http://127.0.0.1:${port}/health`
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await httpGet(url, 2000)
      if (res.statusCode === 200) return true
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

/** 开发态：Vite 实时编译；打包态：API 内嵌的 frontend/dist */
function resolveUiUrl(apiPort) {
  const devUi = String(process.env.DOC_INTEL_UI_URL || '').trim()
  if (!app.isPackaged && devUi.startsWith('http://')) return devUi
  return `http://127.0.0.1:${apiPort}/`
}

async function verifyDevUiUrl(url) {
  try {
    const res = await httpGet(url, 8000)
    if (res.statusCode !== 200) return false
    return (res.body || '').includes('electron-glass')
  } catch {
    return false
  }
}

/** 确认 API 内嵌 dist 为 Electron 毛玻璃版（非 desktop-local 像素风） */
async function verifyElectronFrontend(port) {
  try {
    const res = await httpGet(`http://127.0.0.1:${port}/`, 8000)
    if (res.statusCode !== 200) return false
    const html = res.body || ''
    if (!html.includes('electron-glass')) return false
    const cssMatch = html.match(/\/assets\/(index-[A-Za-z0-9_-]+\.css)/)
    if (!cssMatch) return false
    const cssRes = await httpGet(`http://127.0.0.1:${port}/assets/${cssMatch[1]}`, 8000)
    if (cssRes.statusCode !== 200) return false
    const css = cssRes.body || ''
    return css.includes('glass-deep') && !css.includes('pixel-paper')
  } catch {
    return false
  }
}

function applyWindowResize(mouseX, mouseY) {
  if (!windowResizeSession?.win || windowResizeSession.win.isDestroyed()) return
  const { edge, startMouseX, startMouseY, startBounds, win } = windowResizeSession
  const dx = mouseX - startMouseX
  const dy = mouseY - startMouseY
  let x = startBounds.x
  let y = startBounds.y
  let width = startBounds.width
  let height = startBounds.height

  if (edge.includes('e')) {
    width = Math.max(WINDOW_MIN_WIDTH, startBounds.width + dx)
  }
  if (edge.includes('w')) {
    width = Math.max(WINDOW_MIN_WIDTH, startBounds.width - dx)
    x = startBounds.x + (startBounds.width - width)
  }
  if (edge.includes('s')) {
    height = Math.max(WINDOW_MIN_HEIGHT, startBounds.height + dy)
  }
  if (edge.includes('n')) {
    height = Math.max(WINDOW_MIN_HEIGHT, startBounds.height - dy)
    y = startBounds.y + (startBounds.height - height)
  }

  win.setBounds({
    x: Math.round(x),
    y: Math.round(y),
    width: Math.round(width),
    height: Math.round(height),
  })
}

/** 截取窗口所在显示器桌面，供前端 filter:blur 强磨砂（CSS backdrop-filter 在 Win 上无法模糊桌面） */
async function captureDesktopBackdropForWindow(win) {
  if (!win || win.isDestroyed()) return null
  const bounds = win.getBounds()
  const display = screen.getDisplayMatching(bounds)
  const scale = display.scaleFactor || 1
  const dw = display.bounds.width
  const dh = display.bounds.height
  const thumbW = Math.min(4096, Math.round(dw * scale))
  const thumbH = Math.min(4096, Math.round(dh * scale))

  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: thumbW, height: thumbH },
  })

  const displayIdStr = String(display.id)
  const source =
    sources.find((s) => s.display_id === displayIdStr) ||
    sources.find((s) => String(s.display_id) === displayIdStr) ||
    sources[0]

  if (!source?.thumbnail || source.thumbnail.isEmpty()) return null

  const dataUrl = source.thumbnail.toDataURL()
  return {
    dataUrl,
    displayWidth: dw,
    displayHeight: dh,
    offsetX: bounds.x - display.bounds.x,
    offsetY: bounds.y - display.bounds.y,
  }
}

async function pushDesktopBackdrop(win, { hideWindow = false } = {}) {
  if (!win || win.isDestroyed() || backdropCaptureInFlight) return
  backdropCaptureInFlight = true
  let prevOpacity
  try {
    if (hideWindow) {
      prevOpacity = win.getOpacity()
      win.setOpacity(0)
      await new Promise((r) => setTimeout(r, 90))
    }
    const payload = await captureDesktopBackdropForWindow(win)
    if (payload && !win.isDestroyed()) {
      win.webContents.send('desktop:backdrop', payload)
    }
  } catch (err) {
    console.warn('[desktop backdrop]', err?.message || err)
  } finally {
    if (hideWindow && prevOpacity !== undefined && !win.isDestroyed()) {
      win.setOpacity(prevOpacity)
    }
    backdropCaptureInFlight = false
  }
}

function scheduleDesktopBackdropRefresh(win, hideWindow = true) {
  if (!usesDesktopBackdropFallback()) return
  if (!win || win.isDestroyed()) return
  if (backdropRefreshTimer) clearTimeout(backdropRefreshTimer)
  backdropRefreshTimer = setTimeout(() => {
    backdropRefreshTimer = null
    pushDesktopBackdrop(win, { hideWindow })
  }, 400)
}

function setupDesktopBackdropHooks(win) {
  if (!usesDesktopBackdropFallback()) return
  if (!win || win.isDestroyed()) return
  const refresh = () => scheduleDesktopBackdropRefresh(win, true)
  win.on('move', refresh)
  win.on('resize', refresh)
}

function registerDesktopBackdropIpc() {
  ipcMain.handle('desktop:getGlassInfo', () => getGlassInfo())
  ipcMain.handle('desktop:capture-backdrop', async (event) => {
    if (!usesDesktopBackdropFallback()) return null
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed()) return null
    return captureDesktopBackdropForWindow(win)
  })
  ipcMain.on('desktop:refresh-backdrop', (event) => {
    if (!usesDesktopBackdropFallback()) return
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed()) return
    scheduleDesktopBackdropRefresh(win, true)
  })
}

function registerWindowResizeIpc() {
  ipcMain.on('window:resize-start', (event, payload) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win || win.isDestroyed() || readWindowMaximizedState(win)) return
    const edge = String(payload?.edge || '')
    if (!edge) return
    windowResizeSession = {
      win,
      edge,
      startMouseX: Number(payload.mouseX) || 0,
      startMouseY: Number(payload.mouseY) || 0,
      startBounds: win.getBounds(),
    }
  })

  ipcMain.on('window:resize-move', (event, payload) => {
    if (!windowResizeSession) return
    if (BrowserWindow.fromWebContents(event.sender) !== windowResizeSession.win) return
    applyWindowResize(Number(payload?.mouseX) || 0, Number(payload?.mouseY) || 0)
  })

  ipcMain.on('window:resize-end', () => {
    windowResizeSession = null
    if (mainWindow && !mainWindow.isDestroyed()) {
      scheduleDesktopBackdropRefresh(mainWindow, true)
    }
  })
}

function registerWindowIpc() {
  registerDesktopBackdropIpc()
  registerWindowResizeIpc()

  const minimizeWindow = (event) => {
    const win = getTargetWindow(event)
    if (win) win.minimize()
  }
  const closeWindow = (event) => {
    const win = getTargetWindow(event)
    if (win) win.close()
  }
  const maximizeWindow = (event) => {
    const win = getTargetWindow(event)
    if (!win) return false
    return toggleWindowMaximize(win)
  }

  ipcMain.on('window:minimize', minimizeWindow)
  ipcMain.on('window:close', closeWindow)
  ipcMain.handle('window:minimize', minimizeWindow)
  ipcMain.handle('window:maximize', maximizeWindow)
  ipcMain.handle('window:close', closeWindow)
  ipcMain.handle('window:isMaximized', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return false
    return readWindowMaximizedState(mainWindow)
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

function applyNativeGlassBackground(win) {
  if (!win || win.isDestroyed()) return

  if (process.platform === 'win32') {
    if (typeof win.setBackgroundColor === 'function') {
      try {
        win.setBackgroundColor('#00000000')
      } catch {
        /* ignore */
      }
    }
    if (typeof win.setBackgroundMaterial === 'function') {
      try {
        /* Win11 原生 Acrylic：窗口级毛玻璃，透出并模糊桌面 */
        win.setBackgroundMaterial(usesNativeWinAcrylic() ? 'acrylic' : 'none')
      } catch {
        /* ignore */
      }
    }
    return
  }
  if (process.platform === 'darwin' && typeof win.setVibrancy === 'function') {
    try {
      win.setVibrancy('under-window')
    } catch {
      /* ignore */
    }
  }
}

function createWindow(url) {
  const iconPath = path.join(appRoot(), 'assets', 'app-icon.ico')
  const winOpts = {
    width: 1280,
    height: 800,
    minWidth: WINDOW_MIN_WIDTH,
    minHeight: WINDOW_MIN_HEIGHT,
    title: APP_TITLE,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    resizable: true,
    maximizable: true,
    minimizable: true,
    fullscreenable: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  }
  if (process.platform === 'win32') {
    if (usesNativeWinAcrylic()) {
      winOpts.backgroundMaterial = 'acrylic'
      winOpts.hasShadow = false
    } else {
      winOpts.hasShadow = true
    }
    winOpts.roundedCorners = true
    winOpts.thickFrame = false
  }
  if (process.platform === 'darwin') {
    winOpts.roundedCorners = true
  }
  if (fs.existsSync(iconPath)) {
    winOpts.icon = iconPath
  }

  mainWindow = new BrowserWindow(winOpts)
  applyNativeGlassBackground(mainWindow)
  mainWindow.setMenuBarVisibility(false)
  mainWindow.removeMenu()
  mainWindow.on('move', () => rememberNormalBounds(mainWindow))
  mainWindow.on('resize', () => rememberNormalBounds(mainWindow))
  mainWindow.on('maximize', () => {
    if (useCustomWindowExpand()) {
      handleWin32MaximizeEvent(mainWindow)
    } else {
      notifyMaximizeState()
    }
    applyNativeGlassBackground(mainWindow)
    applyWinTitleBarOverlay(mainWindow)
  })
  mainWindow.on('unmaximize', () => {
    if (useCustomWindowExpand()) {
      handleWin32UnmaximizeEvent(mainWindow)
    } else {
      notifyMaximizeState()
    }
    applyNativeGlassBackground(mainWindow)
    applyWinTitleBarOverlay(mainWindow)
  })
  mainWindow.on('restore', () => {
    if (useCustomWindowExpand()) {
      handleWin32UnmaximizeEvent(mainWindow)
    }
    applyNativeGlassBackground(mainWindow)
    applyWinTitleBarOverlay(mainWindow)
  })
  setupWin32SysCommandHook(mainWindow)
  mainWindow.once('ready-to-show', () => {
    applyNativeGlassBackground(mainWindow)
    normalWindowBounds = mainWindow.getBounds()
    applyWinTitleBarOverlay(mainWindow)
    if (process.platform === 'win32' && typeof mainWindow.setBackgroundColor === 'function') {
      mainWindow.setBackgroundColor('#00000000')
    }
    mainWindow.show()
  })
  mainWindow.loadURL(url)

  mainWindow.webContents.on('did-finish-load', () => {
    applyNativeGlassBackground(mainWindow)
    if (process.platform === 'win32' && typeof mainWindow.setBackgroundColor === 'function') {
      mainWindow.setBackgroundColor('#00000000')
    }
    mainWindow.webContents.send('desktop:glass-info', getGlassInfo())
    if (usesDesktopBackdropFallback()) {
      pushDesktopBackdrop(mainWindow, { hideWindow: false })
    }
  })

  setupDesktopBackdropHooks(mainWindow)

  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith('http://') || target.startsWith('https://')) {
      shell.openExternal(target)
    }
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    resetWindowExpandState()
    mainWindow = null
  })
}

async function boot() {
  const envPort = parseInt(process.env.DESKTOP_API_PORT || '', 10)
  if (Number.isFinite(envPort) && envPort > 0) {
    apiPort = envPort
  } else {
    stopLocalStaleApis()
    await new Promise((r) => setTimeout(r, 800))
    apiPort = await pickApiPort()
  }

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

  const uiUrl = resolveUiUrl(apiPort)
  const usingViteDev = uiUrl !== `http://127.0.0.1:${apiPort}/`

  const uiOk = usingViteDev
    ? await verifyDevUiUrl(uiUrl)
    : await verifyElectronFrontend(apiPort)
  if (!uiOk) {
    killBackend()
    dialog.showErrorBox(
      APP_TITLE,
      usingViteDev
        ? `开发前端未就绪：${uiUrl}\n\n请先运行 scripts\\run_dev.ps1（会启动 Vite）。`
        : `端口 ${apiPort} 上的界面不是 Electron 毛玻璃版（可能被旧进程占用）。\n\n` +
            '请运行 scripts\\build.ps1 重新打包，或结束旧 DocumentIntelligenceApi 进程。',
    )
    app.quit()
    return
  }

  createWindow(uiUrl)
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
      createWindow(resolveUiUrl(apiPort))
    }
  })
}
