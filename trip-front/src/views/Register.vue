<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { register } from '@/api/user'

const router = useRouter()
const message = useMessage()
const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)

const onRegister = async () => {
  if (!username.value.trim()) { message.warning('请输入用户名'); return }
  if (!email.value.trim()) { message.warning('请输入邮箱'); return }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) { message.warning('邮箱格式不正确'); return }
  if (!password.value || password.value.length < 6) { message.warning('密码不能少于6位'); return }
  if (password.value !== confirmPassword.value) { message.warning('两次输入的密码不一致'); return }
  loading.value = true
  try {
    const res: any = await register({ username: username.value.trim(), email: email.value.trim(), password: password.value })
    if (res.code === 200) {
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      message.success('注册成功')
      router.replace('/')
    } else {
      message.error(res.error || '注册失败')
    }
  } catch {
    message.error('注册失败，请重试')
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
        <h2>创建账号</h2>
        <p class="auth-subtitle">注册你的 TripAI 账号</p>
      </div>
      <n-form @submit.prevent="onRegister">
        <n-form-item label="用户名" path="username">
          <n-input v-model:value="username" placeholder="请输入用户名" :disabled="loading" />
        </n-form-item>
        <n-form-item label="邮箱" path="email">
          <n-input v-model:value="email" placeholder="请输入邮箱" :disabled="loading" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input v-model:value="password" type="password" placeholder="请输入密码（至少6位）" :disabled="loading" show-password-on="click" />
        </n-form-item>
        <n-form-item label="确认密码" path="confirmPassword">
          <n-input v-model:value="confirmPassword" type="password" placeholder="请再次输入密码" :disabled="loading" show-password-on="click" />
        </n-form-item>
        <n-button type="primary" block strong :loading="loading" attr-type="submit" size="large">
          注册
        </n-button>
      </n-form>
      <div class="auth-links" style="justify-content: center;">
        <router-link to="/login">已有账号？去登录</router-link>
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
  justify-content: center;
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
