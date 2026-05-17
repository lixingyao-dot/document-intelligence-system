<script setup>
import { ref } from 'vue'
import WorkflowSidebar from './WorkflowSidebar.vue'
import WorkflowCanvas from './WorkflowCanvas.vue'
import WorkflowConfig from './WorkflowConfig.vue'
import SidebarToggle from '../common/SidebarToggle.vue'

const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
</script>

<template>
  <div class="workflow-view" :class="{ 'left-collapsed': leftCollapsed, 'right-collapsed': rightCollapsed }">
    <div class="sidebar-panel left-sidebar" :class="{ collapsed: leftCollapsed }">
      <WorkflowSidebar />
      <SidebarToggle
        side="left"
        :collapsed="leftCollapsed"
        collapse-title="收起左侧栏"
        expand-title="展开左侧栏"
        @toggle="leftCollapsed = !leftCollapsed"
      />
    </div>

    <WorkflowCanvas />

    <div class="sidebar-panel right-sidebar" :class="{ collapsed: rightCollapsed }">
      <WorkflowConfig />
      <SidebarToggle
        side="right"
        :collapsed="rightCollapsed"
        collapse-title="收起右侧栏"
        expand-title="展开右侧栏"
        @toggle="rightCollapsed = !rightCollapsed"
      />
    </div>
  </div>
</template>
