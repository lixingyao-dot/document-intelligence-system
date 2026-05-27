<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Minus, Square, Copy, X } from 'lucide-vue-next'
import { getDesktopWindowApi } from '../../utils/desktopShell'

const appVersion = __APP_VERSION__
const maximized = ref(false)
let unsubscribe = null

onMounted(async () => {
  const win = getDesktopWindowApi()
  if (!win) return
  try {
    maximized.value = await win.isMaximized()
  } catch {
    /* ignore */
  }
  if (win.onMaximizedChanged) {
    unsubscribe = win.onMaximizedChanged((v) => {
      maximized.value = Boolean(v)
    })
  }
})

onUnmounted(() => {
  unsubscribe?.()
})

function getWin() {
  return window.docIntelDesktop?.window ?? getDesktopWindowApi()
}

function onMinimizeClick(event) {
  event.stopPropagation()
  getWin()?.minimize?.()
}

async function onMaximizeClick(event) {
  event.stopPropagation()
  const win = getWin()
  if (!win?.maximizeToggle) return
  try {
    maximized.value = Boolean(await win.maximizeToggle())
  } catch {
    /* ignore */
  }
}

function onCloseClick(event) {
  event.stopPropagation()
  getWin()?.close?.()
}
</script>

<template>
  <header class="electron-titlebar">
    <div class="titlebar-left" @dblclick="onMaximizeClick">
      <img class="titlebar-icon" src="/app-icon.png" alt="" width="18" height="18" />
      <span class="titlebar-title">文档智能系统</span>
      <span class="titlebar-badge">Electron · {{ appVersion }}</span>
    </div>
    <div class="titlebar-drag-fill" aria-hidden="true" @dblclick="onMaximizeClick" />

    <div class="titlebar-controls">
      <button type="button" class="win-btn" title="最小化" aria-label="最小化" @click.stop="onMinimizeClick">
        <Minus :size="14" :stroke-width="2.5" />
      </button>
      <button
        type="button"
        class="win-btn"
        :title="maximized ? '还原' : '最大化'"
        :aria-label="maximized ? '还原' : '最大化'"
        @click.stop="onMaximizeClick"
      >
        <Copy v-if="maximized" :size="13" :stroke-width="2.5" />
        <Square v-else :size="12" :stroke-width="2.5" />
      </button>
      <button type="button" class="win-btn win-btn-close" title="关闭" aria-label="关闭" @click.stop="onCloseClick">
        <X :size="14" :stroke-width="2.5" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.electron-titlebar {
  flex-shrink: 0;
  height: var(--electron-titlebar-height, 40px);
  min-height: var(--electron-titlebar-height, 40px);
  display: flex;
  align-items: stretch;
  position: relative;
  width: 100%;
  z-index: 100000;
  pointer-events: auto;
  background: rgba(16, 16, 22, 0.92);
  border-bottom: 1px solid rgba(255, 255, 255, 0.28);
  isolation: isolate;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

.titlebar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 100%;
  padding: 0 14px;
  min-width: 0;
  flex-shrink: 0;
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.titlebar-drag-fill {
  flex: 1 1 auto;
  min-width: 24px;
  height: 100%;
  -webkit-app-region: drag;
  app-region: drag;
}

.titlebar-icon {
  flex-shrink: 0;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  pointer-events: none;
}

.titlebar-title {
  font-size: 13px;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  text-shadow: 0 0 1px rgba(0, 0, 0, 0.35);
}

.titlebar-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  color: #bfdbfe;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  pointer-events: none;
}

.titlebar-controls {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  z-index: 100010;
  pointer-events: auto;
  -webkit-app-region: no-drag !important;
  app-region: no-drag !important;
}

.win-btn {
  width: 46px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.18);
  background: transparent;
  color: #ffffff;
  cursor: pointer;
  transition: background 0.12s ease;
  pointer-events: auto;
  -webkit-app-region: no-drag !important;
  app-region: no-drag !important;
  -webkit-font-smoothing: antialiased;
}

.win-btn :deep(svg) {
  pointer-events: none;
}

.win-btn:hover {
  background: rgba(255, 255, 255, 0.14);
}

.win-btn-close:hover {
  background: #dc2626;
  color: #fff;
}
</style>
