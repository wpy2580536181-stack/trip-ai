<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { forgotPassword, resetPassword } from '@/api/user'

const router = useRouter()
const message = useMessage()

const step = ref<'email' | 'reset'>('email')
const email = ref('')
const token = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)

const sendResetCode = async () => {
  if (!email.value.trim()) { message.warning('请输入邮箱'); return }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) { message.warning('邮箱格式不正确'); return }
  loading.value = true
  try {
    const res: any = await forgotPassword(email.value.trim())
    if (res.code === 200) {
      token.value = res.data?.token || ''
      step.value = 'reset'
      message.success('验证码已发送到您的邮箱')
    } else {
      message.error(res.error || '发送失败')
    }
  } catch {
    message.error('发送失败，请重试')
  } finally {
    loading.value = false
  }
}

const onReset = async () => {
  if (!token.value.trim()) { message.warning('请输入验证码'); return }
  if (!newPassword.value || newPassword.value.length < 6) { message.warning('新密码不能少于6位'); return }
  if (newPassword.value !== confirmPassword.value) { message.warning('两次输入的密码不一致'); return }
  loading.value = true
  try {
    const res: any = await resetPassword({ email: email.value.trim(), token: token.value.trim(), newPassword: newPassword.value })
    if (res.code === 200) {
      message.success('密码重置成功，请登录')
      router.push('/login')
    } else {
      message.error(res.error || '重置失败')
    }
  } catch {
    message.error('重置失败，请重试')
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
        <h2>重置密码</h2>
        <p class="auth-subtitle">通过注册邮箱重置你的密码</p>
      </div>
      <div v-if="step === 'email'">
        <n-form @submit.prevent="sendResetCode">
          <n-form-item label="邮箱" path="email">
            <n-input v-model:value="email" type="email" placeholder="请输入注册时使用的邮箱" :disabled="loading" />
          </n-form-item>
          <n-button type="primary" block strong :loading="loading" attr-type="submit" size="large">
            获取验证码
          </n-button>
        </n-form>
      </div>
      <div v-else>
        <n-form @submit.prevent="onReset">
          <n-form-item label="验证码" path="token">
            <n-input v-model:value="token" placeholder="请输入邮箱收到的验证码" :disabled="loading" />
          </n-form-item>
          <n-form-item label="新密码" path="newPassword">
            <n-input v-model:value="newPassword" type="password" placeholder="请输入新密码（至少6位）" :disabled="loading" show-password-on="click" />
          </n-form-item>
          <n-form-item label="确认密码" path="confirmPassword">
            <n-input v-model:value="confirmPassword" type="password" placeholder="请再次输入新密码" :disabled="loading" show-password-on="click" />
          </n-form-item>
          <n-button type="primary" block strong :loading="loading" attr-type="submit" size="large">
            重置密码
          </n-button>
        </n-form>
      </div>
      <div class="auth-links" style="justify-content: center;">
        <router-link to="/login">返回登录</router-link>
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
