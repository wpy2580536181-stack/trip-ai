import { createRouter, createWebHistory } from 'vue-router'
import { isTokenExpired, clearAuth } from '../utils/auth'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/about',
    name: 'About',
    component: () => import('../views/About.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/Profile.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/Chat.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/detail',
    name: 'Detail',
    component: () => import('../views/Detail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/History.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/knowledge',
    name: 'KnowledgeManager',
    component: () => import('../views/KnowledgeManager.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/token-usage',
    name: 'TokenUsage',
    component: () => import('../views/TokenUsage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/feedback',
    name: 'AdminFeedback',
    component: () => import('../views/AdminFeedbackDashboard.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/reset-password',
    name: 'ResetPassword',
    component: () => import('../views/ResetPassword.vue'),
    meta: { guestOnly: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const valid = !!token && !isTokenExpired(token)

  // 需要登录的页面 + token 无效 → 跳登录
  if (to.meta.requiresAuth && !valid) {
    if (token) {
      console.warn('[Auth] Token 已过期或无效，清除并跳登录')
      clearAuth()
    }
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }
  // 需要 admin 角色（roleId=1）
  if (to.meta.requiresAdmin) {
    const userInfo = localStorage.getItem('userInfo')
    let roleId = 0
    if (userInfo) {
      try { roleId = JSON.parse(userInfo).roleId ?? 0 } catch { /* ignore */ }
    }
    if (roleId !== 1) {
      console.warn('[Auth] 非 admin 用户访问', to.fullPath)
      next({ name: 'Home' })
      return
    }
  }
  // 已登录用户访问游客页面（登录/注册/重置密码），重定向到首页
  if (to.meta.guestOnly && valid) {
    next({ name: 'Home' })
    return
  }
  next()
})

export default router