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
  border: 1px solid var(--border-color);
  border-radius: 12px;
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
