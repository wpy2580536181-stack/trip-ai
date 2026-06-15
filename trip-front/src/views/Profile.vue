<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showConfirmDialog } from 'vant'
import { getUserInfo, updateUserInfo, changePassword } from '@/api/user'
import type { UserPreferences } from '@/api/user'

const router = useRouter()
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

// 编辑表单
const editForm = ref({
  nickname: '',
  phone: '',
  bio: '',
})

// 修改密码表单
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
    showToast('获取用户信息失败')
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
      showToast('偏好已保存')
    } else {
      showToast(res.error || '保存失败')
    }
  } catch {
    showToast('保存失败')
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
      showToast('更新成功')
      isEdit.value = false
    } else {
      showToast(res.error || '更新失败')
    }
  } catch {
    showToast('更新失败')
  } finally {
    loading.value = false
  }
}

const onChangePassword = async () => {
  if (!passwordForm.value.oldPassword) {
    showToast('请输入原密码')
    return
  }
  if (!passwordForm.value.newPassword || passwordForm.value.newPassword.length < 6) {
    showToast('新密码不能少于6位')
    return
  }
  if (passwordForm.value.newPassword !== passwordForm.value.confirmPassword) {
    showToast('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    const res: any = await changePassword({
      oldPassword: passwordForm.value.oldPassword,
      newPassword: passwordForm.value.newPassword,
    })
    if (res.code === 200) {
      showToast('密码修改成功')
      showPasswordDialog.value = false
      passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
    } else {
      showToast(res.error || '修改失败')
    }
  } catch {
    showToast('修改失败')
  } finally {
    loading.value = false
  }
}

const onLogout = async () => {
  try {
    await showConfirmDialog({ title: '提示', message: '确定要退出登录吗？' })
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    router.replace('/login')
  } catch {
    // 用户取消
  }
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
    <van-nav-bar title="个人中心" left-arrow @click-left="router.back()" />

    <div class="profile-card">
      <div class="avatar-section">
        <van-icon name="manager-o" size="60" color="#1989fa" />
        <div class="user-basic">
          <h3>{{ userInfo.nickname || userInfo.username }}</h3>
          <span class="role-tag">{{ roleName(userInfo.roleId) }}</span>
        </div>
      </div>
    </div>

    <!-- 查看模式 -->
    <div v-if="!isEdit" class="info-section">
      <van-cell-group inset>
        <van-cell title="用户名" :value="userInfo.username" />
        <van-cell title="邮箱" :value="userInfo.email" />
        <van-cell title="昵称" :value="userInfo.nickname || '未设置'" />
        <van-cell title="手机号" :value="userInfo.phone || '未设置'" />
        <van-cell title="简介" :value="userInfo.bio || '未设置'" />
        <van-cell title="注册时间" :value="userInfo.createdAt?.split('T')[0]" />
      </van-cell-group>

      <van-cell-group inset title="旅行偏好" class="preferences-section">
        <van-cell title="旅行风格">
          <template #value>
            <van-radio-group v-model="preferences.travelStyle" direction="horizontal">
              <van-radio name="cultural">文化</van-radio>
              <van-radio name="nature">自然</van-radio>
              <van-radio name="food">美食</van-radio>
              <van-radio name="leisure">休闲</van-radio>
            </van-radio-group>
          </template>
        </van-cell>
        <van-cell title="预算档次">
          <template #value>
            <van-radio-group v-model="preferences.budgetLevel" direction="horizontal">
              <van-radio name="economy">经济</van-radio>
              <van-radio name="standard">标准</van-radio>
              <van-radio name="comfort">舒适</van-radio>
              <van-radio name="luxury">豪华</van-radio>
            </van-radio-group>
          </template>
        </van-cell>
        <van-cell title="节奏">
          <template #value>
            <van-radio-group v-model="preferences.pace" direction="horizontal">
              <van-radio name="compact">紧凑</van-radio>
              <van-radio name="moderate">适中</van-radio>
              <van-radio name="relaxed">轻松</van-radio>
            </van-radio-group>
          </template>
        </van-cell>
        <van-cell title="避开高峰" center>
          <template #right-icon>
            <van-switch v-model="preferences.avoidCrowds" />
          </template>
        </van-cell>
        <van-cell title="兴趣标签">
          <template #value>
            <van-checkbox-group v-model="preferences.interests" direction="horizontal" class="interests-group">
              <van-checkbox name="摄影">📷 摄影</van-checkbox>
              <van-checkbox name="美食">🍜 美食</van-checkbox>
              <van-checkbox name="历史">🏛️ 历史</van-checkbox>
              <van-checkbox name="自然">🏞️ 自然</van-checkbox>
              <van-checkbox name="购物">🛍️ 购物</van-checkbox>
              <van-checkbox name="冒险">🧗 冒险</van-checkbox>
              <van-checkbox name="亲子">👨‍👩‍👧 亲子</van-checkbox>
              <van-checkbox name="夜生活">🌙 夜生活</van-checkbox>
            </van-checkbox-group>
          </template>
        </van-cell>
      </van-cell-group>

      <div class="action-buttons">
        <van-button type="primary" block round :disabled="!preferencesDirty" @click="onSavePreferences">
          保存偏好
        </van-button>
        <van-button type="primary" block round @click="startEdit">编辑资料</van-button>
        <van-button plain block round @click="showPasswordDialog = true">修改密码</van-button>
        <van-button plain block round type="danger" @click="onLogout">退出登录</van-button>
      </div>
    </div>

    <!-- 编辑模式 -->
    <div v-else class="info-section">
      <van-cell-group inset>
        <van-field v-model="editForm.nickname" label="昵称" placeholder="请输入昵称" />
        <van-field v-model="editForm.phone" label="手机号" placeholder="请输入手机号" type="tel" />
        <van-field v-model="editForm.bio" label="简介" placeholder="请输入简介" type="textarea" rows="3" maxlength="255" show-word-limit />
      </van-cell-group>

      <div class="action-buttons">
        <van-button type="primary" block round :loading="loading" @click="saveEdit">保存</van-button>
        <van-button plain block round @click="isEdit = false">取消</van-button>
      </div>
    </div>

    <!-- 修改密码弹窗 -->
    <van-dialog v-model:show="showPasswordDialog" title="修改密码" show-confirm-button show-cancel-button @confirm="onChangePassword">
      <div style="padding: 16px">
        <van-field v-model="passwordForm.oldPassword" type="password" label="原密码" placeholder="请输入原密码" />
        <van-field v-model="passwordForm.newPassword" type="password" label="新密码" placeholder="请输入新密码（至少6位）" />
        <van-field v-model="passwordForm.confirmPassword" type="password" label="确认密码" placeholder="请再次输入新密码" />
      </div>
    </van-dialog>
  </div>
</template>

<style scoped>
.profile-page {
  min-height: 100vh;
  background: #f7f8fa;
}

.profile-card {
  background: #fff;
  padding: 24px 16px;
  margin-bottom: 12px;
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-basic h3 {
  margin: 0 0 4px 0;
  font-size: 18px;
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

.action-buttons {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.interests-group {
  flex-wrap: wrap;
  gap: 8px;
}
</style>