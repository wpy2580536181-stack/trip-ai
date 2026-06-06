<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { login } from '@/api/user'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)

const onLogin = async () => {
  if (!username.value.trim()) {
    showToast('请输入用户名')
    return
  }
  if (!password.value.trim()) {
    showToast('请输入密码')
    return
  }
  loading.value = true
  try {
    const res: any = await login({
      username: username.value.trim(),
      password: password.value,
    })
    if (res.code === 200) {
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      showToast('登录成功')
      const redirect = router.currentRoute.value.query.redirect as string
      router.replace(redirect || '/')
    } else {
      showToast(res.error || '登录失败')
    }
  } catch {
    showToast('登录失败，请重试')
  } finally {
    loading.value = false
  }
}

const goToRegister = () => {
  router.push('/register')
}

const goToResetPassword = () => {
  router.push('/reset-password')
}
</script>

<template>
  <div class="login-page">
    <div class="login-header">
      <h2>欢迎回来</h2>
      <p>登录您的旅游助手账号</p>
    </div>
    <div class="login-form">
      <van-cell-group inset>
        <van-field
          v-model="username"
          label="用户名"
          placeholder="请输入用户名/邮箱"
          :rules="[{ required: true, message: '请输入用户名' }]"
        />
        <van-field
          v-model="password"
          type="password"
          label="密码"
          placeholder="请输入密码"
          :rules="[{ required: true, message: '请输入密码' }]"
        />
      </van-cell-group>
      <div class="login-actions">
        <van-button type="primary" block round :loading="loading" @click="onLogin">
          登录
        </van-button>
      </div>
      <div class="login-links">
        <span class="link" @click="goToRegister">没有账号？去注册</span>
        <span class="link" @click="goToResetPassword">忘记密码？</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px;
  background: #f7f8fa;
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.login-header h2 {
  font-size: 28px;
  color: #323233;
  margin-bottom: 8px;
}

.login-header p {
  font-size: 14px;
  color: #969799;
}

.login-actions {
  padding: 24px 16px;
}

.login-links {
  display: flex;
  justify-content: space-between;
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