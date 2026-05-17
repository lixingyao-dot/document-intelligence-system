/**
 * 保存智能对话生成文件：Electron 下弹出系统「另存为」，Web 回退为浏览器下载。
 */

function desktopApi() {
  return typeof window !== 'undefined' ? window.docIntelDesktop : null
}

function resolveFileName(fileInfo) {
  return String(fileInfo?.file_name || fileInfo?.name || 'download').trim() || 'download'
}

function resolveSourcePath(fileInfo) {
  return String(fileInfo?.file_path || fileInfo?.path || '').trim()
}

function fallbackBrowserDownload(url, fileName) {
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function blobToBase64(blob) {
  const buffer = await blob.arrayBuffer()
  let binary = ''
  const bytes = new Uint8Array(buffer)
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

async function fetchAsBlob(url) {
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) {
    throw new Error(`下载失败 (${res.status})`)
  }
  return res.blob()
}

function buildDownloadUrl(fileInfo, sessionId) {
  const docId = fileInfo?.library_doc_id || fileInfo?.doc_id
  if (docId) {
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    return {
      url: `${baseUrl}/api/library/docs/${encodeURIComponent(docId)}/download`,
      fileName: resolveFileName(fileInfo),
    }
  }
  if (fileInfo?.file_id && sessionId && !String(fileInfo.file_id).includes('-')) {
    return {
      url: `/api/sessions/${encodeURIComponent(sessionId)}/files/${encodeURIComponent(fileInfo.file_id)}/download`,
      fileName: resolveFileName(fileInfo),
    }
  }
  const sourcePath = resolveSourcePath(fileInfo)
  if (sourcePath) {
    return {
      url: `/api/files/download?path=${encodeURIComponent(sourcePath)}`,
      fileName: resolveFileName(fileInfo),
    }
  }
  return null
}

/**
 * @param {object} fileInfo
 * @param {{ sessionId?: string }} options
 * @returns {Promise<{ ok: boolean, savedPath?: string, canceled?: boolean, error?: string }>}
 */
export async function saveResultFile(fileInfo, options = {}) {
  const fileName = resolveFileName(fileInfo)
  const sessionId = options.sessionId || ''
  const api = desktopApi()
  const sourcePath = resolveSourcePath(fileInfo)

  if (api?.dialog?.saveFile && sourcePath) {
    const result = await api.dialog.saveFile({
      sourcePath,
      defaultName: fileName,
    })
    if (result?.ok && result.savedPath) {
      return { ok: true, savedPath: result.savedPath }
    }
    if (result?.canceled) {
      return { ok: false, canceled: true }
    }
    if (result?.error === 'source_not_found') {
      /* fall through to fetch */
    } else if (result?.error) {
      return { ok: false, error: result.error }
    }
  }

  const target = buildDownloadUrl(fileInfo, sessionId)
  if (!target?.url) {
    return { ok: false, error: 'no_file_source' }
  }

  if (api?.dialog?.saveFileFromBuffer) {
    try {
      const blob = await fetchAsBlob(target.url)
      const base64 = await blobToBase64(blob)
      const result = await api.dialog.saveFileFromBuffer({
        base64,
        defaultName: target.fileName || fileName,
      })
      if (result?.ok) {
        return { ok: true, savedPath: result.savedPath }
      }
      if (result?.canceled) {
        return { ok: false, canceled: true }
      }
      return { ok: false, error: result?.error || 'save_failed' }
    } catch (err) {
      return { ok: false, error: String(err?.message || err) }
    }
  }

  fallbackBrowserDownload(target.url, target.fileName || fileName)
  return { ok: true, savedPath: '' }
}

export function saveResultFileLabel(fileInfo) {
  const name = resolveFileName(fileInfo)
  const ext = name.includes('.') ? name.split('.').pop().toUpperCase() : ''
  if (fileInfo?.download_label) {
    return `保存 ${fileInfo.download_label}…`
  }
  return ext ? `保存 ${ext}…` : '保存…'
}
