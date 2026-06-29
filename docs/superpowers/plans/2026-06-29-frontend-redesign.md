# 前端 Redesign 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 trip-front 从移动端 Vant 4 + 默认蓝主题改造为桌面端 Naive UI + 暖灰极简风

**Architecture:** 三阶段渐进迁移。先搭建 Naive UI 布局框架（侧边栏 + 内容区），再逐页替换 Vant 组件，最后移除 Vant 依赖并打磨细节。每个页面保留原有逻辑（API 调用、路由守卫、认证机制），仅替换 UI 层。

**Tech Stack:** Vue 3 + Naive UI + TypeScript + Vite

## Global Constraints

- 所有页面保留原有业务逻辑不变（API 调用、表单验证、路由跳转等）
- 样式遵循暖灰色板（见设计文档），不使用 Vant 默认蓝
- 使用 Naive UI n-global-config + darkTheme 实现暗色模式
- 图标优先使用 emoji，精细图标使用 @vicons/ionicons5
- 每个页面改造完成需验证：页面渲染正常、交互正常、功能无退化

---

### Task 1: 项目基础设施 — 安装依赖 + 布局框架 + 主题配置

**Files:**
- Modify: `trip-front/package.json`
- Create: `trip-front/src/styles/theme.ts`
- Create: `trip-front/src/components/layout/AppLayout.vue`
- Create: `trip-front/src/components/layout/Sidebar.vue`
- Modify: `trip-front/src/main.ts`
- Modify: `trip-front/src/App.vue`
- Modify: `trip-front/src/router/index.ts`
- Modify: `trip-front/vite.config.ts`
- Modify: `trip-front/src/style.css`

**Interfaces:**
- Consumes: 现有路由配置、现有页面组件
- Produces: `AppLayout`（布局容器，包裹 router-view）、`Sidebar`（导航侧边栏接收 `collapsed` prop）、`theme.ts`（导出 Naive UI 主题配置）

- [ ] **Step 1: 安装 Naive UI 依赖**

```bash
pnpm add naive-ui @vicons/ionicons5
```

- [ ] **Step 2: 创建主题配置文件 `src/styles/theme.ts`**

```typescript
import type { GlobalThemeOverrides } from 'naive-ui'

export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#665CA2',
    primaryColorHover: '#7B6FB8',
    primaryColorPressed: '#554A8E',
    bodyColor: '#FCFAFA',
    cardColor: '#F5F2ED',
    modalColor: '#F5F2ED',
    dividerColor: '#EAE5E0',
    textColor1: '#2B2D31',
    textColor2: '#6C6E74',
    textColor3: '#9B9BA0',
    borderRadius: '12px',
    fontSize: '14px',
    fontSizeSmall: '12px',
    fontSizeMedium: '14px',
    fontSizeLarge: '16px',
    heightMedium: '40px',
  },
  Button: {
    borderRadius: '10px',
    fontWeight: '600',
    colorPrimary: '#665CA2',
    colorHoverPrimary: '#7B6FB8',
    colorPressedPrimary: '#554A8E',
  },
  Card: {
    borderRadius: '12px',
    borderColor: '#EAE5E0',
  },
  Input: {
    borderRadius: '8px',
    border: '1px solid #EAE5E0',
    borderHover: '1px solid #665CA2',
    borderFocus: '1px solid #665CA2',
  },
  Tag: {
    borderRadius: '6px',
  },
}

export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#8B7FD4',
    primaryColorHover: '#9E93E0',
    primaryColorPressed: '#776CCC',
    bodyColor: '#1E1E20',
    cardColor: '#262628',
    modalColor: '#262628',
    dividerColor: '#2E2E32',
    textColor1: '#E4E4E4',
    textColor2: '#9B9BA0',
    textColor3: '#6C6E74',
    borderRadius: '12px',
    fontSize: '14px',
    heightMedium: '40px',
  },
  Button: {
    borderRadius: '10px',
    fontWeight: '600',
    colorPrimary: '#8B7FD4',
    colorHoverPrimary: '#9E93E0',
    colorPressedPrimary: '#776CCC',
  },
  Card: {
    borderRadius: '12px',
    borderColor: '#2E2E32',
  },
  Input: {
    borderRadius: '8px',
    border: '1px solid #2E2E32',
    borderHover: '1px solid #8B7FD4',
    borderFocus: '1px solid #8B7FD4',
  },
  Tag: {
    borderRadius: '6px',
  },
}
```

- [ ] **Step 3: 创建侧边栏组件 `src/components/layout/Sidebar.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NButton } from 'naive-ui'

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
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary, #2B2D31);
}

.nav-item.active {
  background: rgba(102, 92, 162, 0.12);
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
```

- [ ] **Step 4: 创建布局组件 `src/components/layout/AppLayout.vue`**

```vue
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
```

- [ ] **Step 5: 重写 `App.vue`**

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  NConfigProvider,
  NMessageProvider,
  darkTheme,
  type GlobalThemeOverrides,
} from 'naive-ui'
import { lightThemeOverrides, darkThemeOverrides } from './styles/theme'
import AppLayout from './components/layout/AppLayout.vue'

const route = useRoute()
const isDark = ref(false)

const theme = computed(() => isDark.value ? darkTheme : null)
const themeOverrides = computed<GlobalThemeOverrides>(
  () => isDark.value ? darkThemeOverrides : lightThemeOverrides
)

const isGuestPage = computed(() => {
  return ['Login', 'Register', 'ResetPassword'].includes(route.name as string)
})
</script>

<template>
  <n-config-provider :theme="theme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <AppLayout v-if="!isGuestPage" :is-dark="isDark" @toggle-theme="isDark = !isDark">
        <router-view />
      </AppLayout>
      <router-view v-else />
    </n-message-provider>
  </n-config-provider>
</template>
```

- [ ] **Step 6: 更新 `main.ts`**

```typescript
import { createApp } from 'vue'
import router from './router'
import './style.css'
import './styles/common.css'
import App from './App.vue'
import { checkAndCleanExpiredToken } from './utils/auth'

checkAndCleanExpiredToken()

const app = createApp(App)
app.use(router)
app.mount('#app')
```

- [ ] **Step 7: 更新 `router/index.ts` — 为每个页面添加 `name`（如果缺少）**

验证所有路由的 `name` 字段都已设置且与页面名称匹配。Login 的 name 应为 'Login'。不需要大改路由，只需确认 name 字段可用于判断游客页面。

- [ ] **Step 8: 更新 `vite.config.ts` — 移除 Vant 自动导入**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:3000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 9: 更新 `src/style.css`**

```css
:root {
  --bg-primary: #FCFAFA;
  --bg-secondary: #F5F2ED;
  --border-color: #EAE5E0;
  --accent: #665CA2;
  --text-primary: #2B2D31;
  --text-secondary: #6C6E74;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: var(--bg-primary);
  color: var(--text-primary);
}

* {
  box-sizing: border-box;
}
```

- [ ] **Step 10: 精简 `src/styles/common.css`**

```css
.page-container {
  width: 100%;
}

.streaming-cursor {
  display: inline-block;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
```

- [ ] **Step 11: 验证布局框架**

```bash
cd /Users/wang/Documents/trip/trip-front
pnpm run dev
```

预期：应用可以启动，无编译错误。登录页应该正常显示（页面居中，没有侧边栏），其他页面会显示侧边栏布局框架 + 原有内容（Vant 组件暂未替换，会出现样式问题，但在预期内）。

---

### Task 2: 游客页面 — Login / Register / ResetPassword

**Files:**
- Modify: `trip-front/src/views/Login.vue`
- Modify: `trip-front/src/views/Register.vue`
- Modify: `trip-front/src/views/ResetPassword.vue`

**Interfaces:**
- Consumes: 游客页面不进入 AppLayout，由 App.vue 判断 `isGuestPage` 直接渲染
- Produces: Naive UI 风格的居中卡片式认证页面

- [ ] **Step 1: 重写 `Login.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { login } from '@/api/user'

const router = useRouter()
const message = useMessage()
const username = ref('')
const password = ref('')
const loading = ref(false)

const onLogin = async () => {
  if (!username.value.trim()) { message.warning('请输入用户名'); return }
  if (!password.value.trim()) { message.warning('请输入密码'); return }
  loading.value = true
  try {
    const res: any = await login({ username: username.value.trim(), password: password.value })
    if (res.code === 200) {
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      message.success('登录成功')
      const redirect = router.currentRoute.value.query.redirect as string
      router.replace(redirect || '/')
    } else {
      message.error(res.error || '登录失败')
    }
  } catch {
    message.error('登录失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <div class="auth-logo">✦</div>
        <h2>欢迎回来</h2>
        <p class="auth-subtitle">登录你的 TripAI 账号</p>
      </div>
      <n-form @submit.prevent="onLogin">
        <n-form-item label="用户名 / 邮箱" path="username">
          <n-input v-model:value="username" placeholder="请输入用户名或邮箱" :disabled="loading" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input v-model:value="password" type="password" placeholder="请输入密码" :disabled="loading" show-password-on="click" />
        </n-form-item>
        <n-button type="primary" block strong :loading="loading" attr-type="submit" size="large">
          登录
        </n-button>
      </n-form>
      <div class="auth-links">
        <router-link to="/register">没有账号？去注册</router-link>
        <router-link to="/reset-password">忘记密码？</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F5F2ED;
  padding: 24px;
}

.auth-card {
  background: #fff;
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  border: 1px solid #EAE5E0;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}

.auth-logo {
  font-size: 40px;
  margin-bottom: 12px;
}

.auth-header h2 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #2B2D31;
}

.auth-subtitle {
  font-size: 14px;
  color: #6C6E74;
  margin: 0;
}

.auth-links {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
  font-size: 13px;
}

.auth-links a {
  color: #665CA2;
  text-decoration: none;
}

.auth-links a:hover {
  text-decoration: underline;
}
</style>
```

- [ ] **Step 2: 按同样模式重写 `Register.vue`**

替换 `van-field` 为 `n-input`，`van-button` 为 `n-button`，`showToast` 为 `message.*`，布局改为居中卡片式。原有注册逻辑（调用 register API、校验等）不变。

- [ ] **Step 3: 按同样模式重写 `ResetPassword.vue`**

替换所有 Vant 组件和 `showToast`，布局改为居中卡片式。

- [ ] **Step 4: 验证游客页面**

```bash
cd /Users/wang/Documents/trip/trip-front && pnpm run dev
```

预期：登录页显示居中白色卡片，表单元素为 Naive UI 风格，紫色强调色。注册和重置密码页风格一致。

---

### Task 3: 首页 — Home.vue

**Files:**
- Modify: `trip-front/src/views/Home.vue`

**Interfaces:**
- Consumes: AppLayout 侧边栏布局、Naive UI 组件、现有业务逻辑（API 调用）
- Produces: 居左排版首页（大标题 + 表单 + 热门目的地网格）

- [ ] **Step 1: 重写 Home.vue**

替换内容：
- 移除 `van-nav-bar`（侧边栏已有导航）
- 移除 `van-notice-bar`
- `van-field` → `n-input`（城市选择改为简化的搜索/下拉模式，去掉 van-picker 底部弹出）
- `van-button` → `n-button`
- `van-cell` → 自定义卡片样式
- `van-grid` / `van-grid-item` → CSS grid
- `van-popup` + `van-picker` → City 选择改为 `n-select`
- `showToast` → `useMessage().*`

布局改为：左对齐大标题 + 副标题，表单区域固定在合适宽度，热门目的地用 grid auto-fill 自适应列数。

注意：城市选择器从底部弹出 Picker 改为 n-select 下拉，移除 showDeparturePicker / showCityPicker 相关模板和逻辑。

- [ ] **Step 2: 验证首页**

确认表单提交、城市选择、热门目的地点击功能正常。

---

### Task 4: 聊天页 — Chat.vue

**Files:**
- Modify: `trip-front/src/views/Chat.vue`

**Interfaces:**
- Consumes: AppLayout 侧边栏布局、Naive UI 组件、SSE 流式 API
- Produces: Claude 风格双栏聊天页（左侧对话历史列表 + 右侧聊天区）

- [ ] **Step 1: 重写 Chat.vue**

关键变更：
- 布局改为：左侧对话历史列表（240px 面板）+ 右侧聊天区（全宽填充）
- 聊天气泡样式改为暖灰极简（用户气泡紫色底白字，AI 气泡白底灰边框）
- `showToast` → `message.*`
- 底部输入框使用 `n-input` textarea 模式
- Markdown 渲染（marked）保持不变
- 保留 SSE 流式聊天逻辑不变

---

### Task 5: 个人相关页 — Profile.vue / TokenUsage.vue / About.vue

**Files:**
- Modify: `trip-front/src/views/Profile.vue`
- Modify: `trip-front/src/views/TokenUsage.vue`
- Modify: `trip-front/src/views/About.vue`

**Interfaces:**
- Consumes: AppLayout 布局、Naive UI 组件
- Produces: 桌面端配置面板风格的个人中心、Token 统计页

- [ ] **Step 1: 重写 Profile.vue**

替换 Vant 组件（`van-cell-group`、`van-field`、`van-button`、`van-tag`、`van-switch`、`van-checkbox` 等）为 Naive UI 等价组件。布局改为桌面面板风格。

- [ ] **Step 2: 重写 TokenUsage.vue**

替换 Vant 组件，保留数据卡片和柱状图（纯 CSS 实现）逻辑。

- [ ] **Step 3: 重写 About.vue**

简单替换，内容居中展示。

---

### Task 6: 行程页 — Detail.vue / History.vue

**Files:**
- Modify: `trip-front/src/views/Detail.vue`
- Modify: `trip-front/src/views/History.vue`

- [ ] **Step 1: 重写 Detail.vue**

替换 `van-collapse` 为 `n-collapse`，`van-tag` 为 `n-tag`，删除 `van-nav-bar`。Day Cards 全宽布局，时间段时间线保持。

- [ ] **Step 2: 重写 History.vue**

替换列表项组件，使用 `n-data-table` 或自定义卡片列表。

---

### Task 7: 管理页面 — Knowledge / Feedback / Trace / Architecture

**Files:**
- Modify: `trip-front/src/views/KnowledgeManager.vue`
- Modify: `trip-front/src/views/AdminFeedbackDashboard.vue`
- Modify: `trip-front/src/views/AdminTrace.vue`
- Modify: `trip-front/src/views/AdminArchitecture.vue`

- [ ] **Step 1: 重写 KnowledgeManager.vue**

表格部分使用 `n-data-table`，表单使用 `n-form`，标签使用 `n-tag`，分页使用 `n-pagination`。

- [ ] **Step 2: 重写 AdminFeedbackDashboard.vue**

统计卡片使用 `n-card`，表格使用 `n-data-table`，保留纯 CSS 柱状图。

- [ ] **Step 3: 重写 AdminTrace.vue**

`van-steps` → `n-steps`，折叠面板 → `n-collapse`。

- [ ] **Step 4: 重写 AdminArchitecture.vue**

VueFlow 组件不变。仅移除 Vant 相关代码（如有）。

---

### Task 8: 收尾清理

**Files:**
- Modify: `trip-front/package.json`
- Modify: `trip-front/vite.config.ts`（已更新）
- Delete: VantResolver 相关配置（已删除）

- [ ] **Step 1: 移除 Vant 依赖**

```bash
pnpm remove vant unplugin-auto-import unplugin-vue-components
```

- [ ] **Step 2: 全局验证所有页面**

```bash
cd /Users/wang/Documents/trip/trip-front
pnpm run dev
```

逐一浏览所有 14 个页面，确认：
- 无 Vant 相关控制台错误
- 所有页面渲染正常
- 暗色模式切换正常
- 侧边栏折叠/展开正常
- 路由守卫正常工作（登录/未登录/Admin 权限）

- [ ] **Step 3: 构建验证**

```bash
pnpm run build
```

确认无 TypeScript 编译错误。

- [ ] **Step 4: 提交**

```bash
git add trip-front/
git commit -m "refactor: 前端 UI 重设计 — Vant 迁移至 Naive UI，暖灰极简风格，桌面端布局"
```
