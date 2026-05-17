<script setup>
import { ref } from 'vue'
import LibrarySidebar from './LibrarySidebar.vue'
import DocGrid from './DocGrid.vue'
import SidebarToggle from '../common/SidebarToggle.vue'

const leftCollapsed = ref(false)
</script>

<template>
  <div class="library-view">
    <!-- Toolbar -->
    <div class="library-toolbar">
      <div class="library-title">
        <span>文档库管理</span>
      </div>
    </div>

    <!-- Body: Sidebar + Content -->
    <div class="library-body">
      <div class="sidebar-panel library-sidebar-panel" :class="{ collapsed: leftCollapsed }">
        <LibrarySidebar />
        <SidebarToggle
          side="left"
          :collapsed="leftCollapsed"
          collapse-title="收起侧栏"
          expand-title="展开侧栏"
          @toggle="leftCollapsed = !leftCollapsed"
        />
      </div>
      <DocGrid />
    </div>
  </div>
</template>

<style scoped>
.library-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

/* Toolbar */
.library-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 32px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.library-title {
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Body */
.library-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}
</style>
