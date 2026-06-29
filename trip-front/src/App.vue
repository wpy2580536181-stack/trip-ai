<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  darkTheme,
  type GlobalThemeOverrides,
} from 'naive-ui'
import { lightThemeOverrides, darkThemeOverrides } from './styles/theme'
import AppLayout from './components/layout/AppLayout.vue'

const route = useRoute()
const isDark = ref(false)

const theme = computed(() => isDark.value ? darkTheme : null)
const themeOverrides = computed<GlobalThemeOverrides>(
  () => isDark.value ? darkThemeOverrides : lightThemeOverrides
)

const isGuestPage = computed(() => {
  return ['Login', 'Register', 'ResetPassword'].includes(route.name as string)
})
</script>

<template>
  <n-config-provider :theme="theme" :theme-overrides="themeOverrides">
    <n-dialog-provider>
      <n-message-provider>
        <AppLayout v-if="!isGuestPage" :is-dark="isDark" @toggle-theme="isDark = !isDark">
          <router-view :key="$route.fullPath" />
        </AppLayout>
        <router-view v-else />
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>
