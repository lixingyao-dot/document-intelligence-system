/**
 * 预加载：暴露 Electron 壳标识与窗口控制（自定义标题栏）。
 */
const { contextBridge, ipcRenderer } = require('electron')
const os = require('os')

function isWindows11OrLater() {
  if (process.platform !== 'win32') return false
  const build = parseInt(String(os.release()).split('.')[2] || '0', 10)
  return build >= 22000
}

function resolveGlassMode() {
  if (process.platform === 'win32') {
    return isWindows11OrLater() ? 'native-acrylic' : 'screenshot-fallback'
  }
  if (process.platform === 'darwin') return 'native-vibrancy'
  return 'none'
}

const glassMode = resolveGlassMode()

const nativeWindowControls = false

contextBridge.exposeInMainWorld('docIntelDesktop', {
  kind: 'electron',
  platform: process.platform,
  isWindows11: isWindows11OrLater(),
  nativeWindowControls,
  titleBarHeight: 40,
  glassMode,
  dialog: {
    pickDirectory: () => ipcRenderer.invoke('dialog:pickDirectory'),
    saveFile: (opts) => ipcRenderer.invoke('dialog:saveFile', opts),
    saveFileFromBuffer: (opts) => ipcRenderer.invoke('dialog:saveFileFromBuffer', opts),
  },
  shell: {
    openPath: (targetPath) => ipcRenderer.invoke('shell:openPath', targetPath),
  },
  desktop: {
    getGlassInfo: () => ipcRenderer.invoke('desktop:getGlassInfo'),
    captureBackdrop: () => ipcRenderer.invoke('desktop:capture-backdrop'),
    refreshBackdrop: () => ipcRenderer.send('desktop:refresh-backdrop'),
    onGlassInfo: (callback) => {
      if (typeof callback !== 'function') return () => {}
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('desktop:glass-info', listener)
      return () => ipcRenderer.removeListener('desktop:glass-info', listener)
    },
    onBackdropUpdated: (callback) => {
      if (typeof callback !== 'function') return () => {}
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('desktop:backdrop', listener)
      return () => ipcRenderer.removeListener('desktop:backdrop', listener)
    },
  },
  window: {
    minimize: () => ipcRenderer.send('window:minimize'),
    maximizeToggle: () => ipcRenderer.invoke('window:maximize'),
    close: () => ipcRenderer.send('window:close'),
    isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
    startResize: (edge, mouseX, mouseY) =>
      ipcRenderer.send('window:resize-start', { edge, mouseX, mouseY }),
    moveResize: (mouseX, mouseY) => ipcRenderer.send('window:resize-move', { mouseX, mouseY }),
    endResize: () => ipcRenderer.send('window:resize-end'),
    onMaximizedChanged: (callback) => {
      if (typeof callback !== 'function') return () => {}
      const listener = (_event, value) => callback(Boolean(value))
      ipcRenderer.on('window:maximized-changed', listener)
      return () => ipcRenderer.removeListener('window:maximized-changed', listener)
    },
  },
})
