/**
 * 预加载：暴露 Electron 壳标识与窗口控制（自定义标题栏）。
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('docIntelDesktop', {
  kind: 'electron',
  dialog: {
    pickDirectory: () => ipcRenderer.invoke('dialog:pickDirectory'),
    saveFile: (opts) => ipcRenderer.invoke('dialog:saveFile', opts),
    saveFileFromBuffer: (opts) => ipcRenderer.invoke('dialog:saveFileFromBuffer', opts),
  },
  shell: {
    openPath: (targetPath) => ipcRenderer.invoke('shell:openPath', targetPath),
  },
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    maximizeToggle: () => ipcRenderer.invoke('window:maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
    onMaximizedChanged: (callback) => {
      if (typeof callback !== 'function') return () => {}
      const listener = (_event, value) => callback(Boolean(value))
      ipcRenderer.on('window:maximized-changed', listener)
      return () => ipcRenderer.removeListener('window:maximized-changed', listener)
    },
  },
})
