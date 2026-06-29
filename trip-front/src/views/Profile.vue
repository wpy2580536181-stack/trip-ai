<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { getUserInfo, updateUserInfo, changePassword } from '@/api/user'
import type { UserPreferences } from '@/api/user'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const isEdit = ref(false)
const loading = ref(false)

interface UserInfo {
  id: number
  username: string
  email: string
  nickname: string
  avatar: string | null
  phone: string | null
  bio: string | null
  roleId: number
  preferences?: UserPreferences | null
  createdAt: string
}

const userInfo = ref<UserInfo>({
  id: 0,
  username: '',
  email: '',
  nickname: '',
  avatar: null,
  phone: null,
  bio: null,
  roleId: 2,
  createdAt: '',
})

const preferences = ref<UserPreferences>({})
const originalPreferences = ref<UserPreferences>({})

const editForm = ref({
  nickname: '',
  phone: '',
  bio: '',
})

const showPasswordDialog = ref(false)
const passwordForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const fetchUserInfo = async () => {
  try {
    const res: any = await getUserInfo()
    if (res.code === 200) {
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      preferences.value = (res.data?.preferences as UserPreferences) ?? {}
      originalPreferences.value = { ...preferences.value }
    }
  } catch {
    message.error('获取用户信息失败')
  }
}

const preferencesDirty = computed(
  () => JSON.stringify(preferences.value) !== JSON.stringify(originalPreferences.value),
)

const onSavePreferences = async () => {
  try {
    const res: any = await updateUserInfo({ preferences: preferences.value })
    if (res.code === 200) {
      originalPreferences.value = { ...preferences.value }
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      message.success('偏好已保存')
    } else {
      message.error(res.error || '保存失败')
    }
  } catch {
    message.error('保存失败')
  }
}

const startEdit = () => {
  editForm.value = {
    nickname: userInfo.value.nickname || '',
    phone: userInfo.value.phone || '',
    bio: userInfo.value.bio || '',
  }
  isEdit.value = true
}

const saveEdit = async () => {
  loading.value = true
  try {
    const res: any = await updateUserInfo(editForm.value)
    if (res.code === 200) {
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
      message.success('更新成功')
      isEdit.value = false
    } else {
      message.error(res.error || '更新失败')
    }
  } catch {
    message.error('更新失败')
  } finally {
    loading.value = false
  }
}

const onChangePassword = async () => {
  if (!passwordForm.value.oldPassword) {
    message.warning('请输入原密码')
    return
  }
  if (!passwordForm.value.newPassword || passwordForm.value.newPassword.length < 6) {
    message.warning('新密码不能少于6位')
    return
  }
  if (passwordForm.value.newPassword !== passwordForm.value.confirmPassword) {
    message.warning('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    const res: any = await changePassword({
      oldPassword: passwordForm.value.oldPassword,
      newPassword: passwordForm.value.newPassword,
    })
    if (res.code === 200) {
      message.success('密码修改成功')
      showPasswordDialog.value = false
      passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
    } else {
      message.error(res.error || '修改失败')
    }
  } catch {
    message.error('修改失败')
  } finally {
    loading.value = false
  }
}

const onLogout = () => {
  dialog.warning({
    title: '提示',
    content: '确定要退出登录吗？',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: () => {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      router.replace('/login')
    },
  })
}

const roleName = (roleId: number) => {
  return roleId === 1 ? '管理员' : '普通用户'
}

onMounted(() => {
  const stored = localStorage.getItem('userInfo')
  if (stored) {
    try {
      userInfo.value = JSON.parse(stored)
    } catch {
      // ignore
    }
  }
  fetchUserInfo()
})
</script>

<template>
  <div class="profile-page">
    <div class="page-header">
      <button class="back-btn" @click="router.back()">←</button>
      <h2>个人中心</h2>
    </div>

    <div class="profile-card">
      <div class="avatar-section">
        <span class="avatar-emoji">👤</span>
        <div class="user-basic">
          <h3>{{ userInfo.nickname || userInfo.username }}</h3>
          <span class="role-tag">{{ roleName(userInfo.roleId) }}</span>
        </div>
      </div>
    </div>

    <div v-if="!isEdit" class="info-section">
      <div class="card">
        <div class="info-row">
          <span class="info-label">用户名</span>
          <span class="info-value">{{ userInfo.username }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">邮箱</span>
          <span class="info-value">{{ userInfo.email }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">昵称</span>
          <span class="info-value">{{ userInfo.nickname || '未设置' }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">手机号</span>
          <span class="info-value">{{ userInfo.phone || '未设置' }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">简介</span>
          <span class="info-value">{{ userInfo.bio || '未设置' }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">注册时间</span>
          <span class="info-value">{{ userInfo.createdAt?.split('T')[0] }}</span>
        </div>
      </div>

      <div class="card">
        <div class="section-title">旅行偏好</div>

        <div class="pref-row">
          <span class="pref-label">旅行风格</span>
          <n-radio-group v-model:value="preferences.travelStyle">
            <n-radio value="cultural">文化</n-radio>
            <n-radio value="nature">自然</n-radio>
            <n-radio value="food">美食</n-radio>
            <n-radio value="leisure">休闲</n-radio>
          </n-radio-group>
        </div>

        <div class="pref-row">
          <span class="pref-label">预算档次</span>
          <n-radio-group v-model:value="preferences.budgetLevel">
            <n-radio value="economy">经济</n-radio>
            <n-radio value="standard">标准</n-radio>
            <n-radio value="comfort">舒适</n-radio>
            <n-radio value="luxury">豪华</n-radio>
          </n-radio-group>
        </div>

        <div class="pref-row">
          <span class="pref-label">节奏</span>
          <n-radio-group v-model:value="preferences.pace">
            <n-radio value="compact">紧凑</n-radio>
            <n-radio value="moderate">适中</n-radio>
            <n-radio value="relaxed">轻松</n-radio>
          </n-radio-group>
        </div>

        <div class="pref-row">
          <span class="pref-label">避开高峰</span>
          <n-switch v-model:value="preferences.avoidCrowds" />
        </div>

        <div class="pref-row">
          <span class="pref-label">兴趣标签</span>
          <n-checkbox-group v-model:value="preferences.interests" class="interests-group">
            <n-checkbox value="摄影">📷 摄影</n-checkbox>
            <n-checkbox value="美食">🍜 美食</n-checkbox>
            <n-checkbox value="历史">🏛️ 历史</n-checkbox>
            <n-checkbox value="自然">🏞️ 自然</n-checkbox>
            <n-checkbox value="购物">🛍️ 购物</n-checkbox>
            <n-checkbox value="冒险">🧗 冒险</n-checkbox>
            <n-checkbox value="亲子">👨‍👩‍👧 亲子</n-checkbox>
            <n-checkbox value="夜生活">🌙 夜生活</n-checkbox>
          </n-checkbox-group>
        </div>
      </div>

      <div class="action-buttons">
        <n-button type="primary" block strong :disabled="!preferencesDirty" @click="onSavePreferences">
          保存偏好
        </n-button>
        <n-button type="primary" block strong @click="startEdit">编辑资料</n-button>
        <n-button quaternary block @click="showPasswordDialog = true">修改密码</n-button>
        <n-button quaternary block style="color: #d03050" @click="onLogout">退出登录</n-button>
      </div>
    </div>

    <div v-else class="info-section">
      <div class="card">
        <n-form>
          <n-form-item label="昵称">
            <n-input v-model:value="editForm.nickname" placeholder="请输入昵称" />
          </n-form-item>
          <n-form-item label="手机号">
            <n-input v-model:value="editForm.phone" placeholder="请输入手机号" />
          </n-form-item>
          <n-form-item label="简介">
            <n-input
              v-model:value="editForm.bio"
              type="textarea"
              placeholder="请输入简介"
              :rows="3"
              :maxlength="255"
              show-count
            />
          </n-form-item>
        </n-form>
      </div>

      <div class="action-buttons">
        <n-button type="primary" block strong :loading="loading" @click="saveEdit">保存</n-button>
        <n-button quaternary block @click="isEdit = false">取消</n-button>
      </div>
    </div>

    <n-modal v-model:show="showPasswordDialog" title="修改密码" preset="dialog" :show-icon="false">
      <template #header>
        <span>修改密码</span>
      </template>
      <div class="password-form">
        <n-form>
          <n-form-item label="原密码">
            <n-input v-model:value="passwordForm.oldPassword" type="password" placeholder="请输入原密码" show-password-on="click" />
          </n-form-item>
          <n-form-item label="新密码">
            <n-input v-model:value="passwordForm.newPassword" type="password" placeholder="请输入新密码（至少6位）" show-password-on="click" />
          </n-form-item>
          <n-form-item label="确认密码">
            <n-input v-model:value="passwordForm.confirmPassword" type="password" placeholder="请再次输入新密码" show-password-on="click" />
          </n-form-item>
        </n-form>
      </div>
      <template #action>
        <n-button @click="showPasswordDialog = false">取消</n-button>
        <n-button type="primary" :loading="loading" @click="onChangePassword">确认</n-button>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.profile-page {
  width: 100%;
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: var(--bg-secondary, #fff);
  border-bottom: 1px solid var(--border-color, #EAE5E0);
  border-radius: 12px 12px 0 0;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #2B2D31);
}

.back-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  color: var(--text-primary, #2B2D31);
  line-height: 1;
}

.profile-card {
  background: var(--bg-secondary, #fff);
  padding: 24px 20px;
  margin-bottom: 12px;
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.avatar-emoji {
  font-size: 48px;
  line-height: 1;
}

.user-basic h3 {
  margin: 0 0 4px 0;
  font-size: 18px;
  color: var(--text-primary, #2B2D31);
}

.role-tag {
  font-size: 12px;
  background: #e8f4ff;
  color: #1989fa;
  padding: 2px 8px;
  border-radius: 10px;
}

.info-section {
  padding: 0 0 16px 0;
}

.card {
  background: var(--bg-secondary, #fff);
  border: 1px solid var(--border-color, #EAE5E0);
  border-radius: 12px;
  padding: 20px;
  margin: 0 16px 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
}

.info-row + .info-row {
  border-top: 1px solid var(--border-color, #EAE5E0);
}

.info-label {
  color: var(--text-secondary, #6C6E74);
  font-size: 14px;
}

.info-value {
  color: var(--text-primary, #2B2D31);
  font-size: 14px;
  font-weight: 500;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #2B2D31);
  margin-bottom: 16px;
}

.pref-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px 0;
}

.pref-row + .pref-row {
  border-top: 1px solid var(--border-color, #EAE5E0);
}

.pref-label {
  color: var(--text-primary, #2B2D31);
  font-size: 14px;
  min-width: 80px;
}

.action-buttons {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.interests-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.password-form {
  padding: 8px 0;
}
</style>
