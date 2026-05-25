<script setup>
import { onMounted } from 'vue'
import { useTabStore } from './stores/tabStore'
import { useSessionStore } from './stores/sessionStore'
import AppHeader from './components/AppHeader.vue'
import ElectronTitleBar from './components/common/ElectronTitleBar.vue'
import LibraryView from './components/library/LibraryView.vue'
import ChatView from './components/chat/ChatView.vue'
import WorkflowView from './components/workflow/WorkflowView.vue'

const tabStore = useTabStore()
const sessionStore = useSessionStore()

onMounted(() => {
  sessionStore.init()
})
</script>

<template>
  <div class="app electron-shell">
    <div class="glass-scene" aria-hidden="true">
      <div class="glass-orb glass-orb--cyan" />
      <div class="glass-orb glass-orb--violet" />
    </div>
    <ElectronTitleBar />
    <div class="app-layout">
      <AppHeader />

      <main class="main-content">
        <LibraryView v-if="tabStore.currentTab === 'library'" />
        <keep-alive>
          <ChatView v-if="tabStore.currentTab === 'chat'" />
        </keep-alive>
        <WorkflowView v-if="tabStore.currentTab === 'workflow'" />
      </main>
    </div>
  </div>
</template>
