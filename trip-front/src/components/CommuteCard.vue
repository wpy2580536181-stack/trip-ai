<script setup lang="ts">
defineProps<{
  options: {
    mode: string
    duration: string
    distance: string
  }[]
  recommended?: number
}>()

const modeIcons: Record<string, string> = {
  '步行': '🚶',
  '公交': '🚌',
  '驾车': '🚕',
  '骑行': '🚲',
}
</script>

<template>
  <div class="commute-card">
    <div class="commute-header">通勤方案对比</div>
    <div
      v-for="(opt, i) in options"
      :key="i"
      class="commute-item"
      :class="{ recommended: recommended === i }"
    >
      <div
        class="commute-icon"
        :class="{
          walk: opt.mode === '步行',
          transit: opt.mode === '公交',
          drive: opt.mode === '驾车' || opt.mode === '骑行',
        }"
      >
        {{ modeIcons[opt.mode] || '📍' }}
      </div>
      <div class="commute-body">
        <div class="commute-mode">{{ opt.mode }}</div>
      </div>
      <div class="commute-stats">
        <div class="commute-duration">{{ opt.duration }}</div>
        <div class="commute-distance">{{ opt.distance }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.commute-card {
  border: 1px solid #eee;
  border-radius: 12px;
  overflow: hidden;
  margin: 8px 0;
  background: #fff;
}
.commute-header {
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  border-bottom: 1px solid #f0f0f0;
}
.commute-item {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  gap: 12px;
  transition: background 0.15s;
}
.commute-item + .commute-item {
  border-top: 1px solid #f5f5f5;
}
.commute-item.recommended {
  background: #f0f9ff;
  position: relative;
}
.commute-item.recommended::before {
  content: '推荐';
  position: absolute;
  top: 0;
  right: 14px;
  font-size: 10px;
  color: #fff;
  background: #1890ff;
  padding: 1px 8px;
  border-radius: 0 0 6px 6px;
}
.commute-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.commute-icon.walk { background: #e6f7ff; }
.commute-icon.transit { background: #f6ffed; }
.commute-icon.drive { background: #fff7e6; }
.commute-body {
  flex: 1;
  min-width: 0;
}
.commute-mode {
  font-size: 14px;
  font-weight: 500;
  color: #1a1a1a;
}
.commute-stats {
  text-align: right;
  flex-shrink: 0;
}
.commute-duration {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}
.commute-distance {
  font-size: 12px;
  color: #999;
  margin-top: 1px;
}
</style>
