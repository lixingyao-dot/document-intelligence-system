<script setup>
import { computed } from 'vue'

const props = defineProps({
  side: {
    type: String,
    default: 'left',
    validator: (v) => ['left', 'right'].includes(v),
  },
  collapsed: {
    type: Boolean,
    default: false,
  },
  collapseTitle: {
    type: String,
    default: '收起侧栏',
  },
  expandTitle: {
    type: String,
    default: '展开侧栏',
  },
})

defineEmits(['toggle'])

const icon = computed(() => {
  if (props.side === 'left') {
    return props.collapsed ? '▶' : '◀'
  }
  return props.collapsed ? '◀' : '▶'
})

const title = computed(() => (props.collapsed ? props.expandTitle : props.collapseTitle))
</script>

<template>
  <button
    type="button"
    class="panel-edge-toggle"
    :class="`panel-edge-toggle--${side}`"
    :title="title"
    :aria-expanded="!collapsed"
    @click="$emit('toggle')"
  >
    <span class="panel-edge-toggle-icon" aria-hidden="true">{{ icon }}</span>
  </button>
</template>
