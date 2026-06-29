<template>
  <div class="spot-item" v-if="data && data.spot">
    <div class="spot-inner">
      <img v-if="data.imageUrl" :src="data.imageUrl" :alt="data.spot" class="spot-thumb"
        @error="onImageError($event)" />
      <div class="spot-body">
        <div class="spot-name">{{ data.spot }}</div>
        <div class="spot-meta" v-if="data.duration || data.ticket || data.transportation">
          <span v-if="data.duration">🕐 {{ data.duration }}</span>
          <span v-if="data.ticket">🎫 {{ data.ticket }}</span>
          <span v-if="data.transportation">🚗 {{ data.transportation }}</span>
        </div>
        <div class="spot-desc" v-if="data.description">{{ data.description }}</div>
      </div>
    </div>
  </div>
  <div class="spot-item empty" v-else>
    <div class="empty-placeholder">暂无安排</div>
  </div>
</template>

<script setup lang="ts">
defineProps({
  data: {
    type: Object,
    default: () => ({}),
  },
})

const onImageError = (e: Event) => {
  ;(e.target as HTMLImageElement).style.display = 'none'
}
</script>

<style scoped>
.spot-inner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.spot-thumb {
  width: 88px;
  height: 66px;
  object-fit: cover;
  border-radius: 6px;
  background: var(--bg-secondary);
  flex-shrink: 0;
  margin-top: 2px;
}
.spot-body {
  flex: 1;
  min-width: 0;
}
.spot-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  margin-bottom: 4px;
}
.spot-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.spot-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.spot-item {
  padding: 6px 0;
}
.spot-item + .spot-item {
  border-top: 1px solid var(--border-color);
  margin-top: 0;
}
.spot-item.empty {
  padding: 12px 0;
}
.empty-placeholder {
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
  padding: 8px 0;
}
</style>
