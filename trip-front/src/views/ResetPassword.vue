<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { forgotPassword, resetPassword } from '@/api/user'

const router = useRouter()

const step = ref<'email' | 'reset'>('email')
const email = ref('')
const token = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)

const sendResetCode = async () => {
  if (!email.value.trim()) {
    showToast('请输入邮箱')
    return
  }
  loading.value = true
  try {
    const res: any = await forgotPassword(email.value.trim())
    if (res.code === 200) {
      token.value = res.data?.token || ''
      step.value = 'reset'
      showToast('验证码已发送到您的邮箱')
    } else {
      showToast(res.error || '发送失败')
    }
  } catch {
    showToast('发送失败，请重试')
  } finally {
    loading.value = false
  }
}

const onReset = async () => {
  if (!token.value.trim()) {
    showToast('请输入验证码')
    return
  }
  if (!newPassword.value || newPassword.value.length < 6) {
    showToast('新密码不能少于6位')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    showToast('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    const res: any = await resetPassword({
      email: email.value.trim(),
      token: token.value.trim(),
      newPassword: newPassword.value,
    })
    if (res.code === 200) {
      showToast('密码重置成功，请登录')
      router.push('/login')
    } else {
      showToast(res.error || '重置失败')
    }
  } catch {
    showToast('重置失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="reset-page">
    <div class="reset-header">
      <h2>重置密码</h2>
      <p>通过注册邮箱重置您的密码</p>
    </div>

    <div v-if="step === 'email'" class="reset-form">
      <van-cell-group inset>
        <van-field
          v-model="email"
          label="邮箱"
          type="email"
          placeholder="请输入注册时使用的邮箱"
          :rules="[{ required: true, message: '请输入邮箱' }]"
        />
      </van-cell-group>
      <div class="reset-actions">
        <van-button type="primary" block round :loading="loading" @click="sendResetCode">
          获取验证码
        </van-button>
      </div>
    </div>

    <div v-else class="reset-form">
      <van-cell-group inset>
        <van-field
          v-model="token"
          label="验证码"
          placeholder="请输入邮箱收到的验证码"
          :rules="[{ required: true, message: '请输入验证码' }]"
        />
        <van-field
          v-model="newPassword"
          type="password"
          label="新密码"
          placeholder="请输入新密码（至少6位）"
          :rules="[{ required: true, message: '请输入新密码' }]"
        />
        <van-field
          v-model="confirmPassword"
          type="password"
          label="确认密码"
          placeholder="请再次输入新密码"
          :rules="[{ required: true, message: '请确认新密码' }]"
        />
      </van-cell-group>
      <div class="reset-actions">
        <van-button type="primary" block round :loading="loading" @click="onReset">
          重置密码
        </van-button>
      </div>
    </div>

    <div class="reset-links">
      <span class="link" @click="router.push('/login')">返回登录</span>
    </div>
  </div>
</template>

<style scoped>
.reset-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px;
  background: #f7f8fa;
}

.reset-header {
  text-align: center;
  margin-bottom: 40px;
}

.reset-header h2 {
  font-size: 28px;
  color: #323233;
  margin-bottom: 8px;
}

.reset-header p {
  font-size: 14px;
  color: #969799;
}

.reset-actions {
  padding: 24px 16px;
}

.reset-links {
  text-align: center;
  padding: 0 16px;
}

.link {
  color: #1989fa;
  font-size: 14px;
  cursor: pointer;
}

.link:hover {
  opacity: 0.8;
}
</style>
