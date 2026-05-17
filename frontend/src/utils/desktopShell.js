/** 检测是否在 Electron 壳内运行，并封装窗口控制 API */
export function isElectronShell() {
  return typeof window !== 'undefined' && window.docIntelDesktop?.kind === 'electron'
}

export function getDesktopWindowApi() {
  if (!isElectronShell()) return null
  return window.docIntelDesktop?.window ?? null
}

/** 选择工作流外部输出目录（仅 Electron） */
export async function pickOutputFolder() {
  if (!isElectronShell()) return null
  const pick = window.docIntelDesktop?.dialog?.pickDirectory
  if (typeof pick !== 'function') return null
  try {
    return await pick()
  } catch {
    return null
  }
}
