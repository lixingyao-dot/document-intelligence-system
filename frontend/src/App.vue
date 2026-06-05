<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTabStore } from './stores/tabStore'
import { useSessionStore } from './stores/sessionStore'
import AppHeader from './components/AppHeader.vue'
import ElectronTitleBar from './components/common/ElectronTitleBar.vue'
import LibraryView from './components/library/LibraryView.vue'
import ChatView from './components/chat/ChatView.vue'
import WorkflowView from './components/workflow/WorkflowView.vue'
import SettingsModal from './components/SettingsModal.vue'
import WindowResizeHandles from './components/common/WindowResizeHandles.vue'
import { getDesktopWindowApi, isElectronShell } from './utils/desktopShell'

const tabStore = useTabStore()
const sessionStore = useSessionStore()
const showSettings = ref(false)
const isMaximized = ref(false)
const showElectronChrome = computed(
  () =>
    isElectronShell() ||
    document.querySelector('meta[name="doc-intel-ui"]')?.getAttribute('content') === 'electron-glass',
)
const glassMode = ref('none')
const useScreenshotBackdrop = ref(false)
const desktopBackdrop = ref(null)
let unbindMaximize = null
let unbindDesktopBackdrop = null
let unbindGlassInfo = null

function syncElectronChromeClass() {
  const root = document.documentElement
  root.classList.add('electron-glass-opaque')
  root.classList.toggle('electron-native-acrylic', glassMode.value === 'native-acrylic')
  root.classList.toggle('electron-screenshot-frost', glassMode.value === 'screenshot-fallback')
  root.classList.toggle('is-maximized', isMaximized.value)
}

function applyGlassInfo(info) {
  if (!info?.glassMode) return
  glassMode.value = info.glassMode
  useScreenshotBackdrop.value = info.glassMode === 'screenshot-fallback'
  syncElectronChromeClass()
}

const desktopBackdropStyle = computed(() => {
  const payload = desktopBackdrop.value
  if (!payload?.dataUrl) return null
  return {
    backgroundImage: `url(${payload.dataUrl})`,
    backgroundSize: `${payload.displayWidth}px ${payload.displayHeight}px`,
    backgroundPosition: `${-payload.offsetX}px ${-payload.offsetY}px`,
    backgroundRepeat: 'no-repeat',
  }
})

function setupDesktopBackdrop() {
  if (!useScreenshotBackdrop.value) return
  const desktop = window.docIntelDesktop?.desktop
  if (!desktop) return
  unbindDesktopBackdrop = desktop.onBackdropUpdated?.((payload) => {
    if (payload?.dataUrl) desktopBackdrop.value = payload
  }) ?? null
  desktop.captureBackdrop?.().then((payload) => {
    if (payload?.dataUrl) desktopBackdrop.value = payload
  }).catch(() => {})
}

function setupGlassMode() {
  const desktop = window.docIntelDesktop?.desktop
  if (!desktop) return

  applyGlassInfo({
    glassMode: window.docIntelDesktop?.glassMode ?? 'none',
    isWindows11: window.docIntelDesktop?.isWindows11 ?? false,
  })

  unbindGlassInfo = desktop.onGlassInfo?.((info) => {
    applyGlassInfo(info)
    if (info?.glassMode === 'screenshot-fallback') setupDesktopBackdrop()
  }) ?? null

  desktop.getGlassInfo?.().then((info) => {
    applyGlassInfo(info)
    setupDesktopBackdrop()
  }).catch(() => {
    setupDesktopBackdrop()
  })
}

onMounted(async () => {
  document.documentElement.classList.add('electron-glass')
  sessionStore.init()
  const win = getDesktopWindowApi()
  if (!win) {
    syncElectronChromeClass()
    return
  }
  setupGlassMode()
  try {
    isMaximized.value = await win.isMaximized()
  } catch {
    /* ignore */
  }
  syncElectronChromeClass()
  unbindMaximize = win.onMaximizedChanged?.((v) => {
    isMaximized.value = Boolean(v)
    syncElectronChromeClass()
    if (useScreenshotBackdrop.value) {
      window.docIntelDesktop?.desktop?.refreshBackdrop?.()
    }
  }) ?? null
})

onUnmounted(() => {
  unbindMaximize?.()
  unbindDesktopBackdrop?.()
  unbindGlassInfo?.()
  document.documentElement.classList.remove(
    'electron-glass-opaque',
    'electron-native-acrylic',
    'electron-screenshot-frost',
    'is-maximized',
  )
})
</script>

<template>
  <div class="electron-root" :class="{ 'is-maximized': isMaximized }">
    <ElectronTitleBar v-if="showElectronChrome" class="electron-shell-titlebar" />
    <div
      v-if="useScreenshotBackdrop && desktopBackdropStyle"
      class="glass-desktop-bg"
      :style="desktopBackdropStyle"
      aria-hidden="true"
    />
    <div class="glass-blur-layer" aria-hidden="true" />
    <div class="app electron-shell app-outer-glass">
      <div class="app-layout">
        <AppHeader @open-settings="showSettings = true" />

        <main class="main-content">
          <LibraryView v-if="tabStore.currentTab === 'library'" />
          <keep-alive>
            <ChatView v-if="tabStore.currentTab === 'chat'" />
          </keep-alive>
          <WorkflowView v-if="tabStore.currentTab === 'workflow'" />
        </main>
      </div>
    </div>

    <WindowResizeHandles v-if="showElectronChrome" :disabled="isMaximized" />
    <Teleport to="body">
      <SettingsModal v-if="showSettings" @close="showSettings = false" />
    </Teleport>
  </div>
</template>

<style scoped>
.electron-root {
  position: relative;
  width: 100%;
  height: 100vh;
  min-height: 100vh;
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
}

.electron-root.is-maximized {
  padding: 0;
}
</style>
