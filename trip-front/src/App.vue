<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const active = ref(0)

const showTabbar = computed(() => {
  const tabbarRoutes = ['/', '/chat', '/profile']
  return tabbarRoutes.includes(route.path)
})

const pathMap: Record<string, number> = {
  '/': 0,
  '/chat': 1,
  '/profile': 2,
}

watch(
  () => route.path,
  (path: string) => {
    active.value = pathMap[path] ?? 0
  },
  { immediate: true }
)
</script>

<template>
    <div class="app-container">
        <router-view />
        <van-tabbar router v-model="active" v-show="showTabbar">
            <van-tabbar-item to="/" icon="home-o">首页</van-tabbar-item>
            <van-tabbar-item to="/chat" icon="chat-o">对话</van-tabbar-item>
            <van-tabbar-item to="/profile" icon="user-o">我的</van-tabbar-item>
        </van-tabbar>
    </div>
</template>
