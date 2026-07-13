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
    <div class="auth-split">
      <!-- 主导区域：品牌区 -->
      <aside class="auth-aside">
        <div class="brand">
          <div class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none">
              <path d="M2 12.5L21 5l-5.5 16-3.2-6.8L2 12.5z" stroke="#fff" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
            </svg>
          </div>
          <span class="brand-name">TripAI</span>
        </div>
        <div class="aside-copy">
          <h1>规划每一次出发</h1>
          <p>智能行程、实时通勤、周边推荐，一次搞定。</p>
        </div>
        <ul class="aside-points">
          <li>多方式通勤对比，直达最快目的地</li>
          <li>个性化行程与偏好记忆</li>
          <li>知识库景点一键加入计划</li>
        </ul>
      </aside>

      <!-- 主操作区：登录表单 -->
      <section class="auth-card">
        <header class="auth-header">
          <h2>欢迎回来</h2>
          <p class="auth-subtitle">登录你的 TripAI 账号，继续规划旅程</p>
        </header>

        <n-form class="auth-form" @submit.prevent="onLogin">
          <n-form-item label="用户名 / 邮箱" path="username">
            <n-input
              v-model:value="username"
              placeholder="请输入用户名或邮箱"
              :disabled="loading"
              size="large"
            >
              <template #prefix>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                  <circle cx="12" cy="8" r="4" stroke="#9A96A8" stroke-width="1.6"/>
                  <path d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6" stroke="#9A96A8" stroke-width="1.6" stroke-linecap="round"/>
                </svg>
              </template>
            </n-input>
          </n-form-item>

          <n-form-item label="密码" path="password">
            <n-input
              v-model:value="password"
              type="password"
              placeholder="请输入密码"
              :disabled="loading"
              size="large"
              show-password-on="click"
            >
              <template #prefix>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
                  <rect x="5" y="10" width="14" height="10" rx="2" stroke="#9A96A8" stroke-width="1.6"/>
                  <path d="M8 10V7a4 4 0 1 1 8 0v3" stroke="#9A96A8" stroke-width="1.6"/>
                </svg>
              </template>
            </n-input>
          </n-form-item>

          <n-button
            type="primary"
            block
            strong
            :loading="loading"
            attr-type="submit"
            size="large"
            class="auth-submit"
          >
            登录
          </n-button>
        </n-form>

        <div class="auth-links">
          <router-link to="/register">没有账号？去注册</router-link>
          <router-link to="/reset-password">忘记密码？</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(1200px 600px at 100% 0%, #EFEAFB 0%, transparent 60%),
    radial-gradient(900px 500px at 0% 100%, #EAF1FB 0%, transparent 55%),
    #F6F4EF;
}

.auth-split {
  width: 100%;
  max-width: 920px;
  display: flex;
  background: #fff;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 24px 60px -28px rgba(40, 32, 80, 0.35);
  border: 1px solid #ECE7F2;
}

/* 主导区域：品牌区 */
.auth-aside {
  flex: 0 0 42%;
  padding: 48px 40px;
  color: #fff;
  background: linear-gradient(150deg, #6B5FC9 0%, #4F46A8 100%);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.aside-copy h1 {
  font-size: 30px;
  line-height: 1.25;
  font-weight: 700;
  margin: 0 0 12px;
}

.aside-copy p {
  font-size: 14px;
  line-height: 1.6;
  margin: 0;
  color: rgba(255, 255, 255, 0.82);
}

.aside-points {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.aside-points li {
  position: relative;
  padding-left: 26px;
  font-size: 13.5px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.9);
}

.aside-points li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 6px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none'%3E%3Cpath d='M5 13l4 4L19 7' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
}

/* 主操作区：表单 */
.auth-card {
  flex: 1;
  padding: 48px 44px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.auth-header {
  margin-bottom: 28px;
}

.auth-header h2 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #1F2030;
}

.auth-subtitle {
  font-size: 14px;
  color: #6C6E74;
  margin: 0;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.auth-submit {
  margin-top: 12px;
}

.auth-links {
  display: flex;
  justify-content: space-between;
  margin-top: 22px;
  font-size: 13px;
}

.auth-links a {
  color: #665CA2;
  text-decoration: none;
}

.auth-links a:hover {
  text-decoration: underline;
}

/* 响应式：窄屏退化为单列，隐藏品牌区 dense 信息 */
@media (max-width: 720px) {
  .auth-split {
    flex-direction: column;
    max-width: 440px;
  }
  .auth-aside {
    flex: none;
    padding: 32px 28px;
  }
  .aside-points {
    display: none;
  }
  .auth-card {
    padding: 32px 28px;
  }
}
</style>
