<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="about-page">
    <div class="page-header">
      <button class="back-btn" @click="router.back()">←</button>
      <h2>关于</h2>
    </div>
    <div class="card">
      <h1>关于页</h1>
      <n-button type="primary" strong @click="router.push('/')">回首页</n-button>
    </div>
  </div>
</template>

<style scoped>
.about-page {
  min-height: 100vh;
  background: var(--bg-primary, #F5F2ED);
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

.card {
  background: var(--bg-secondary, #fff);
  border: 1px solid var(--border-color, #EAE5E0);
  border-radius: 12px;
  padding: 24px;
  margin: 16px;
  text-align: center;
}

.card h1 {
  font-size: 20px;
  color: var(--text-primary, #2B2D31);
  margin: 0 0 16px 0;
}
</style>
