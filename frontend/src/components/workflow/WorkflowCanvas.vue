<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'
import { resolveWorkflowIcon } from '../../utils/workflowIcons'

const workflowStore = useWorkflowStore()

const canvasAreaRef = ref(null)
const canvasInnerRef = ref(null)

/** 与 .workflow-node 占位、连线锚点一致（紧凑尺寸） */
const NODE_BOX_W = 156
const NODE_BOX_H = 72
const CANVAS_PAD = 280
/** 底部步骤条高度（与 CSS .canvas-step-bar 一致） */
const STEP_BAR_RESERVED_BOTTOM = 52

const DROP_MIME = 'application/x-workflow-node'

/** 是否允许从组件库拖入（放宽以兼容各浏览器 MIME 列表） */
function canAcceptToolboxDrag(e) {
  const types = [...(e.dataTransfer?.types || [])]
  return types.some(
    t =>
      t === DROP_MIME ||
      t === 'text/plain' ||
      t === 'Text'
  )
}

function parseDroppedToolboxItem(e) {
  let raw = ''
  try {
    raw = e.dataTransfer.getData(DROP_MIME)
  } catch (_) {
    /* ignore */
  }
  if (!raw) {
    try {
      raw = e.dataTransfer.getData('text/plain')
    } catch (_) {
      /* ignore */
    }
  }
  if (!raw || raw[0] !== '{') return null
  try {
    const o = JSON.parse(raw)
    if (o && typeof o.schemaKey === 'string' && o.title) return o
  } catch (_) {
    /* ignore */
  }
  return null
}

/** 将指针位置转为 canvas-inner 内坐标（与 node.x / node.y 一致） */
function pointerToInnerLocal(e) {
  const inner = canvasInnerRef.value
  if (!inner) return { x: 30, y: 160 }
  const rect = inner.getBoundingClientRect()
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
}

const dropZoneActive = ref(false)

function onCanvasDragEnter(e) {
  if (!canAcceptToolboxDrag(e)) return
  e.preventDefault()
  dropZoneActive.value = true
}

function onCanvasDragOver(e) {
  if (!canAcceptToolboxDrag(e)) return
  e.preventDefault()
  try {
    e.dataTransfer.dropEffect = 'copy'
  } catch (_) {
    /* ignore */
  }
}

function onCanvasDragLeave(e) {
  const el = canvasAreaRef.value
  if (el && e.relatedTarget && el.contains(e.relatedTarget)) return
  dropZoneActive.value = false
}

function onCanvasDrop(e) {
  dropZoneActive.value = false
  const item = parseDroppedToolboxItem(e)
  if (!item) return
  e.preventDefault()
  e.stopPropagation()
  const { x, y } = pointerToInnerLocal(e)
  workflowStore.addNodeAt(item, x - NODE_BOX_W / 2, y - NODE_BOX_H / 2)
}

// 画布平移：用 scroll 代替 transform，避免 overflow:hidden 裁切节点与连线
const isPanning = ref(false)
const panStart = ref({ mouseX: 0, mouseY: 0, scrollLeft: 0, scrollTop: 0 })

const canvasInnerSize = computed(() => {
  const nodes = workflowStore.canvasNodes
  let maxX = 1200
  let maxY = 900
  if (nodes?.length) {
    for (const n of nodes) {
      maxX = Math.max(maxX, n.x + NODE_BOX_W)
      maxY = Math.max(maxY, n.y + NODE_BOX_H)
    }
    maxX += CANVAS_PAD
    maxY += CANVAS_PAD
  }
  return {
    width: Math.max(1200, maxX),
    height: Math.max(900, maxY),
  }
})

const canvasInnerStyle = computed(() => ({
  width: `${canvasInnerSize.value.width}px`,
  height: `${canvasInnerSize.value.height}px`,
}))

/** 与节点 DOM 坐标系一致，勿扩大 viewBox（否则会与 HTML 节点错位） */
const svgViewBox = computed(() => {
  const { width, height } = canvasInnerSize.value
  return `0 0 ${width} ${height}`
})

// Node drag state
const isDraggingNode = ref(false)
const dragNodeId = ref(null)
const dragStart = ref({ mouseX: 0, mouseY: 0, nodeX: 0, nodeY: 0 })

function handleNodeClick(event, nodeId) {
  event.stopPropagation()
  workflowStore.selectNode(nodeId)
}

function handleNodeDelete(event, nodeId) {
  event.stopPropagation()
  workflowStore.deleteNode(nodeId)
}

// Canvas pan
function onCanvasMouseDown(event) {
  if (event.button !== 0) return
  if (event.target.closest('.workflow-node')) return
  if (event.target.closest('.canvas-step-bar')) return
  const area = canvasAreaRef.value
  isPanning.value = true
  panStart.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    scrollLeft: area?.scrollLeft ?? 0,
    scrollTop: area?.scrollTop ?? 0,
  }
  event.preventDefault()
}

function onCanvasMouseMove(event) {
  if (isPanning.value) {
    const area = canvasAreaRef.value
    if (!area) return
    const dx = event.clientX - panStart.value.mouseX
    const dy = event.clientY - panStart.value.mouseY
    area.scrollLeft = panStart.value.scrollLeft - dx
    area.scrollTop = panStart.value.scrollTop - dy
  } else if (isDraggingNode.value && dragNodeId.value) {
    const dx = event.clientX - dragStart.value.mouseX
    const dy = event.clientY - dragStart.value.mouseY
    workflowStore.updateNodePosition(dragNodeId.value, dragStart.value.nodeX + dx, dragStart.value.nodeY + dy)
  }
}

function onCanvasMouseUp() {
  isPanning.value = false
  isDraggingNode.value = false
  dragNodeId.value = null
}

// Node drag（含输入/输出节点）
function onNodeMouseDown(event, nodeId) {
  const node = workflowStore.canvasNodes.find(n => n.id === nodeId)
  if (!node) return
  event.stopPropagation()
  event.preventDefault()
  isDraggingNode.value = true
  dragNodeId.value = nodeId
  dragStart.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    nodeX: node.x,
    nodeY: node.y
  }
}

/** 将当前节点群居中到可见画布（inner 坐标系内节点位置不变，只调整 pan） */
function fitViewToNodes() {
  const area = canvasAreaRef.value
  const nodes = workflowStore.canvasNodes
  if (!area) return
  if (!nodes?.length) {
    area.scrollLeft = 0
    area.scrollTop = 0
    return
  }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of nodes) {
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + NODE_BOX_W)
    maxY = Math.max(maxY, n.y + NODE_BOX_H)
  }

  const bboxCx = (minX + maxX) / 2
  const bboxCy = (minY + maxY) / 2
  const viewW = area.clientWidth
  const viewH = area.clientHeight
  if (viewW < 1 || viewH < 1) return

  const contentH = Math.max(120, viewH - STEP_BAR_RESERVED_BOTTOM)

  area.scrollLeft = Math.max(0, Math.round(bboxCx - viewW / 2))
  area.scrollTop = Math.max(0, Math.round(bboxCy - contentH / 2))
}

function scheduleFitView() {
  nextTick(() => {
    requestAnimationFrame(() => fitViewToNodes())
  })
}

let resizeObserver = null

onMounted(() => {
  scheduleFitView()
  if (canvasAreaRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => scheduleFitView())
    resizeObserver.observe(canvasAreaRef.value)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

watch(
  () => workflowStore.currentWorkflowId,
  () => scheduleFitView()
)

watch(
  () => workflowStore.canvasNodes.map((n) => n.id).join('\n'),
  () => scheduleFitView()
)

function handleCanvasClick(event) {
  if (event.target.classList.contains('canvas-area') || event.target.classList.contains('canvas-inner')) {
    workflowStore.selectNode(null)
  }
}

/** 连线锚点：右/左端口中心（与 .node-port 垂直居中一致） */
function nodeOutPoint(n) {
  return { x: n.x + NODE_BOX_W, y: n.y + NODE_BOX_H / 2 }
}
function nodeInPoint(n) {
  return { x: n.x, y: n.y + NODE_BOX_H / 2 }
}

/** 水平工作流连线：三次贝塞尔，控制点按水平间距比例伸出 */
function buildConnectionPath(p1, p2) {
  const x1 = p1.x
  const y1 = p1.y
  const x2 = p2.x
  const y2 = p2.y
  const dx = x2 - x1
  const dy = y2 - y1
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)

  if (adx < 1 && ady < 1) {
    return `M ${x1} ${y1}`
  }

  if (ady < 4 && adx > 8) {
    return `M ${x1} ${y1} L ${x2} ${y2}`
  }

  const bend = Math.min(120, Math.max(28, adx * 0.42))
  const sign = dx >= 0 ? 1 : -1
  const c1x = x1 + sign * bend
  const c2x = x2 - sign * bend
  return `M ${x1} ${y1} C ${c1x} ${y1}, ${c2x} ${y2}, ${x2} ${y2}`
}

const connPaths = computed(() => {
  const nodes = workflowStore.canvasNodes
  return nodes.slice(0, -1).map((fromNode, i) => {
    const toNode = nodes[i + 1]
    const pOut = nodeOutPoint(fromNode)
    const pIn = nodeInPoint(toNode)
    return {
      d: buildConnectionPath(pOut, pIn),
      key: `conn-${fromNode.id}-${toNode.id}`,
      fromId: fromNode.id,
      toId: toNode.id
    }
  })
})

const nodeProgressById = computed(() => {
  const map = {}
  ;(workflowStore.nodeProgress || []).forEach(item => {
    if (item?.id) map[item.id] = item
  })
  return map
})

function getNodeRunState(nodeId) {
  return nodeProgressById.value[nodeId]?.status || 'idle'
}

// 当前选中节点在数组中的索引
const selectedIndex = computed(() => {
  if (!workflowStore.selectedNodeId) return -1
  return workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId)
})
</script>

<template>
  <div class="workflow-canvas">
    <!-- Canvas Area -->
    <div
      ref="canvasAreaRef"
      class="canvas-area"
      :class="{ 'is-panning': isPanning, 'canvas-area--drop-target': dropZoneActive }"
      @click="handleCanvasClick"
      @mousedown="onCanvasMouseDown"
      @mousemove="onCanvasMouseMove"
      @mouseup="onCanvasMouseUp"
      @mouseleave="onCanvasMouseUp"
      @dragenter="onCanvasDragEnter"
      @dragover="onCanvasDragOver"
      @dragleave="onCanvasDragLeave"
      @drop="onCanvasDrop"
    >
      <!-- Inner canvas -->
      <div ref="canvasInnerRef" class="canvas-inner" :style="canvasInnerStyle">
        <!-- SVG Connections -->
        <svg
          class="connections-svg"
          :width="canvasInnerSize.width"
          :height="canvasInnerSize.height"
          :viewBox="svgViewBox"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            v-for="cp in connPaths"
            :key="cp.key"
            :d="cp.d"
            class="conn-path"
            :class="{
              'conn-selected':
                workflowStore.selectedNodeId === cp.fromId ||
                workflowStore.selectedNodeId === cp.toId
            }"
          />
        </svg>

        <!-- Nodes -->
        <div
          v-for="(node, i) in workflowStore.canvasNodes"
          :key="node.id"
          class="workflow-node"
          :class="{ selected: workflowStore.selectedNodeId === node.id, ['type-' + node.type]: true, ['run-' + getNodeRunState(node.id)]: true }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @click="handleNodeClick($event, node.id)"
          @mousedown="onNodeMouseDown($event, node.id)"
        >
          <div class="node-selected-badge">当前选中</div>
          <div class="node-port input-port"></div>
          <div class="node-header">
            <div class="node-icon" :class="node.type" aria-hidden="true">
              <component
                :is="resolveWorkflowIcon(node.schemaKey, node.type)"
                :size="14"
                :stroke-width="2"
              />
            </div>
            <span class="node-title">{{ node.title }}</span>
            <span class="node-step-tag">Step {{ i + 1 }}</span>
            <div
              v-if="node.type !== 'input' && node.type !== 'output'"
              class="node-seq-actions"
              @mousedown.stop
              @click.stop
            >
              <button
                type="button"
                class="node-seq-btn"
                :disabled="i <= 1"
                title="前移（更早执行）"
                @click="workflowStore.moveNodeEarlier(node.id)"
              >◀</button>
              <button
                type="button"
                class="node-seq-btn"
                :disabled="i >= workflowStore.canvasNodes.length - 2"
                title="后移（更晚执行）"
                @click="workflowStore.moveNodeLater(node.id)"
              >▶</button>
            </div>
            <button
              v-if="i > 0 && i < workflowStore.canvasNodes.length - 1"
              class="node-delete-btn"
              title="删除节点"
              @click.stop="handleNodeDelete($event, node.id)"
            >×</button>
          </div>
          <div class="node-body">{{ node.body }}</div>
          <div v-if="getNodeRunState(node.id) !== 'idle'" class="node-run-status">
            <span class="node-run-dot"></span>
            <span>{{ nodeProgressById[node.id]?.message || nodeProgressById[node.id]?.status }}</span>
          </div>
          <div class="node-port output-port"></div>
        </div>
      </div>

      <div class="canvas-step-bar canvas-step-bar--bottom">
        <template v-for="(node, i) in workflowStore.canvasNodes" :key="'step-' + node.id">
          <div
            class="step-item"
            :class="{
              'step-done': selectedIndex > -1 && i < selectedIndex,
              'step-active': workflowStore.selectedNodeId === node.id,
              ['run-' + getNodeRunState(node.id)]: true
            }"
            role="button"
            tabindex="0"
            @click.stop="workflowStore.selectNode(node.id)"
          >
            <div class="step-icon" aria-hidden="true">
              <component
                :is="resolveWorkflowIcon(node.schemaKey, node.type)"
                :size="14"
                :stroke-width="2"
              />
            </div>
            <div class="step-num">{{ i + 1 }}</div>
            <div class="step-name">{{ node.title }}</div>
          </div>
          <div v-if="i < workflowStore.canvasNodes.length - 1" class="step-line" :key="'line-' + i"></div>
        </template>
      </div>
    </div>
  </div>
</template>
