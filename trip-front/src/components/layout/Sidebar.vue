<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const props = defineProps<{
  collapsed: boolean
  isDark: boolean
}>()

const emit = defineEmits<{
  (e: 'update:collapsed', val: boolean): void
  (e: 'toggle-theme'): void
}>()

const router = useRouter()
const route = useRoute()

const userInfo = computed(() => {
  try {
    const stored = localStorage.getItem('userInfo')
    return stored ? JSON.parse(stored) : null
  } catch { return null }
})

const isAdmin = computed(() => userInfo.value?.roleId === 1)

const navItems = computed(() => {
  const items = [
    { path: '/', label: '首页', icon: '🏠' },
    { path: '/chat', label: '对话', icon: '💬' },
    { path: '/history', label: '行程', icon: '📋' },
    { path: '/commute', label: '通勤择优', icon: '🧭' },
    { path: '/token-usage', label: 'Tokens', icon: '📊' },
    { path: '/profile', label: '个人', icon: '👤' },
  ]
  if (isAdmin.value) {
    items.push(
      { path: '/knowledge', label: '知识库', icon: '📚' },
      { path: '/admin/feedback', label: '反馈', icon: '📝' },
      { path: '/admin/trace', label: 'Trace', icon: '🔍' },
      { path: '/admin/architecture', label: '架构', icon: '🏗️' },
    )
  }
  return items
})

const navigate = (path: string) => router.push(path)

const isActive = (path: string) =>
  route.path === path || (path !== '/' && route.path.startsWith(path))

const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
  router.push('/login')
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <div class="logo" @click="navigate('/')">
        <span class="logo-icon">✦</span>
        <span v-show="!collapsed" class="logo-text">TripAI</span>
      </div>
    </div>

    <nav class="sidebar-nav">
      <div
        v-for="item in navItems"
        :key="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
        @click="navigate(item.path)"
        :title="item.label"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span v-show="!collapsed" class="nav-label">{{ item.label }}</span>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="nav-item" @click="emit('toggle-theme')" :title="isDark ? '浅色模式' : '深色模式'">
        <span class="nav-icon">{{ isDark ? '☀️' : '🌙' }}</span>
        <span v-show="!collapsed" class="nav-label">{{ isDark ? '浅色' : '深色' }}</span>
      </div>
      <div class="nav-item" @click="logout" title="退出登录">
        <span class="nav-icon">🚪</span>
        <span v-show="!collapsed" class="nav-label">退出</span>
      </div>
      <div class="nav-item" @click="emit('update:collapsed', !collapsed)" :title="collapsed ? '展开' : '折叠'">
        <span class="nav-icon">{{ collapsed ? '→' : '←' }}</span>
        <span v-show="!collapsed" class="nav-label">折叠</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 220px;
  min-width: 220px;
  height: 100vh;
  background: var(--bg-secondary, #F5F2ED);
  border-right: 1px solid var(--border-color, #EAE5E0);
  display: flex;
  flex-direction: column;
  transition: width 0.2s, min-width 0.2s;
  overflow: hidden;
}

.sidebar.collapsed {
  width: 64px;
  min-width: 64px;
}

.sidebar-header {
  padding: 20px 16px 16px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.logo-icon {
  font-size: 24px;
  line-height: 1;
  color: var(--accent, #665CA2);
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #2B2D31);
  white-space: nowrap;
}

.sidebar-nav {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-secondary, #6C6E74);
  transition: all 0.15s;
  white-space: nowrap;
}

.nav-item:hover {
  background: var(--hover-bg);
  color: var(--text-primary, #2B2D31);
}

.nav-item.active {
  background: var(--hover-bg-active);
  color: var(--accent, #665CA2);
  font-weight: 500;
}

.nav-icon {
  font-size: 18px;
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.nav-label {
  font-size: 14px;
  font-weight: 500;
}

.sidebar-footer {
  padding: 8px;
  border-top: 1px solid var(--border-color, #EAE5E0);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
