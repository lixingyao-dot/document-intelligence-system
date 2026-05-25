<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Minus, Square, Copy, X } from 'lucide-vue-next'
import { getDesktopWindowApi } from '../../utils/desktopShell'

const maximized = ref(false)
let unsubscribe = null

const win = getDesktopWindowApi()

onMounted(async () => {
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

function minimize() {
  win?.minimize()
}

function toggleMaximize() {
  win?.maximizeToggle()
}

function closeWindow() {
  win?.close()
}
</script>

<template>
  <header class="electron-titlebar">
    <div class="titlebar-drag" @dblclick="toggleMaximize">
      <img class="titlebar-icon" src="/app-icon.png" alt="" width="18" height="18" />
      <span class="titlebar-title">文档智能系统</span>
      <span class="titlebar-badge">本地版</span>
    </div>

    <div class="titlebar-controls">
      <button type="button" class="win-btn" title="最小化" aria-label="最小化" @click="minimize">
        <Minus :size="14" :stroke-width="2.5" />
      </button>
      <button
        type="button"
        class="win-btn"
        :title="maximized ? '还原' : '最大化'"
        :aria-label="maximized ? '还原' : '最大化'"
        @click="toggleMaximize"
      >
        <Copy v-if="maximized" :size="13" :stroke-width="2.5" />
        <Square v-else :size="12" :stroke-width="2.5" />
      </button>
      <button type="button" class="win-btn win-btn-close" title="关闭" aria-label="关闭" @click="closeWindow">
        <X :size="14" :stroke-width="2.5" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.electron-titlebar {
  flex-shrink: 0;
  height: var(--electron-titlebar-height, 40px);
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  user-select: none;
  -webkit-user-select: none;
}

.titlebar-drag {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  min-width: 0;
  -webkit-app-region: drag;
  app-region: drag;
}

.titlebar-icon {
  flex-shrink: 0;
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 1px 1px 0 rgba(42, 38, 51, 0.35);
  image-rendering: auto;
}

.titlebar-title {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.titlebar-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  color: var(--accent-primary);
  background: rgba(255, 255, 255, 0.92);
  border: 2px solid var(--border-color);
  box-shadow: 2px 2px 0 rgba(42, 38, 51, 0.25);
}

.titlebar-controls {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.win-btn {
  width: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-left: 2px solid rgba(42, 38, 51, 0.2);
  background: transparent;
  color: #fff;
  cursor: pointer;
  transition: background 0.12s ease;
}

.win-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}

.win-btn-close:hover {
  background: #e03131;
  color: #fff;
}
</style>
