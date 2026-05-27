<script setup>
import { getDesktopWindowApi } from '../../utils/desktopShell'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
})

const edges = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function onResizeStart(edge, event) {
  if (props.disabled || event.button !== 0) return
  const win = getDesktopWindowApi()
  if (!win?.startResize) return
  event.preventDefault()
  event.stopPropagation()
  win.startResize(edge, event.screenX, event.screenY)

  const onMove = (e) => {
    win.moveResize?.(e.screenX, e.screenY)
  }
  const onUp = () => {
    win.endResize?.()
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
</script>

<template>
  <div class="window-resize-layer" aria-hidden="true">
    <div
      v-for="edge in edges"
      :key="edge"
      class="window-resize-handle"
      :class="`window-resize-handle--${edge}`"
      @mousedown="onResizeStart(edge, $event)"
    />
  </div>
</template>

<style scoped>
.window-resize-layer {
  position: fixed;
  inset: 0;
  z-index: 20;
  pointer-events: none;
}

.window-resize-handle {
  position: absolute;
  pointer-events: auto;
  -webkit-app-region: no-drag;
  app-region: no-drag;
  background: transparent;
}

.window-resize-handle--n {
  top: var(--electron-titlebar-height, 40px);
  left: 10px;
  right: 10px;
  height: 6px;
  cursor: n-resize;
}

.window-resize-handle--s {
  bottom: 0;
  left: 10px;
  right: 10px;
  height: 6px;
  cursor: s-resize;
}

.window-resize-handle--e {
  top: calc(var(--electron-titlebar-height, 40px) + 4px);
  right: 0;
  bottom: 10px;
  width: 6px;
  cursor: e-resize;
}

.window-resize-handle--w {
  top: calc(var(--electron-titlebar-height, 40px) + 4px);
  left: 0;
  bottom: 10px;
  width: 6px;
  cursor: w-resize;
}

.window-resize-handle--ne {
  top: calc(var(--electron-titlebar-height, 40px) + 4px);
  right: 148px;
  width: 14px;
  height: 14px;
  cursor: ne-resize;
}

.window-resize-handle--nw {
  top: var(--electron-titlebar-height, 40px);
  left: 0;
  width: 14px;
  height: 14px;
  cursor: nw-resize;
}

.window-resize-handle--se {
  right: 0;
  bottom: 0;
  width: 14px;
  height: 14px;
  cursor: se-resize;
}

.window-resize-handle--sw {
  left: calc(var(--sidebar-width, 96px) + 4px);
  bottom: 0;
  width: 14px;
  height: 14px;
  cursor: sw-resize;
}
</style>
