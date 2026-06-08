<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { register } from '@/api/user'

const router = useRouter()
const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)

const onRegister = async () => {
  if (!username.value.trim()) {
    showToast('请输入用户名')
    return
  }
  if (!email.value.trim()) {
    showToast('请输入邮箱')
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
    showToast('邮箱格式不正确')
    return
  }
  if (!password.value || password.value.length < 6) {
    showToast('密码不能少于6位')
    return
  }
  if (password.value !== confirmPassword.value) {
    showToast('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    const res: any = await register({
      username: username.value.trim(),
      email: email.value.trim(),
      password: password.value,
    })
    if (res.code === 200) {
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      showToast('注册成功')
      router.replace('/')
    } else {
      showToast(res.error || '注册失败')
    }
  } catch {
    showToast('注册失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-page">
    <div class="register-header">
      <h2>创建账号</h2>
      <p>注册旅游助手账号</p>
    </div>
    <div class="register-form">
      <van-cell-group inset>
        <van-field
          v-model="username"
          label="用户名"
          placeholder="请输入用户名"
          :rules="[{ required: true, message: '请输入用户名' }]"
        />
        <van-field
          v-model="email"
          label="邮箱"
          type="email"
          placeholder="请输入邮箱"
          :rules="[{ required: true, message: '请输入邮箱' }]"
        />
        <van-field
          v-model="password"
          type="password"
          label="密码"
          placeholder="请输入密码（至少6位）"
          :rules="[{ required: true, message: '请输入密码' }]"
        />
        <van-field
          v-model="confirmPassword"
          type="password"
          label="确认密码"
          placeholder="请再次输入密码"
          :rules="[{ required: true, message: '请确认密码' }]"
        />
      </van-cell-group>
      <div class="register-actions">
        <van-button type="primary" block round :loading="loading" @click="onRegister">
          注册
        </van-button>
      </div>
      <div class="register-links">
        <span class="link" @click="router.push('/login')">已有账号？去登录</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px;
  background: #f7f8fa;
}

.register-header {
  text-align: center;
  margin-bottom: 32px;
}

.register-header h2 {
  font-size: 28px;
  color: #323233;
  margin-bottom: 8px;
}

.register-header p {
  font-size: 14px;
  color: #969799;
}

.register-actions {
  padding: 24px 16px;
}

.register-links {
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