<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from './Sidebar.vue'

defineProps<{
  isDark: boolean
}>()

defineEmits<{
  (e: 'toggle-theme'): void
}>()

const collapsed = ref(false)
</script>

<template>
  <div class="app-layout" :class="{ dark: isDark }">
    <Sidebar v-model:collapsed="collapsed" :is-dark="isDark" @toggle-theme="$emit('toggle-theme')" />
    <main class="main-content" :class="{ collapsed: collapsed }">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  background: #FCFAFA;
  transition: background 0.3s;
}

.app-layout.dark {
  background: #1E1E20;
}

.main-content {
  flex: 1;
  padding: 32px 40px;
  overflow-y: auto;
  min-width: 0;
}
</style>
