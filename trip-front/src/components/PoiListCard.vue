<script setup lang="ts">
defineProps<{
  items: {
    name: string
    distance?: string
    rating?: number
    cost?: string
  }[]
}>()
</script>

<template>
  <div class="poi-card">
    <div class="poi-header">附近地点</div>
    <div v-for="(item, i) in items" :key="i" class="poi-item">
      <div class="poi-rank" :class="{ top3: i < 3 }">{{ i + 1 }}</div>
      <div class="poi-info">
        <div class="poi-name">{{ item.name }}</div>
        <div class="poi-tags">
          <span v-if="item.rating" class="poi-tag poi-rating">★ {{ item.rating }}</span>
          <span v-if="item.cost" class="poi-tag">{{ item.cost }}</span>
        </div>
      </div>
      <div v-if="item.distance" class="poi-distance">{{ item.distance }}</div>
    </div>
  </div>
</template>

<style scoped>
.poi-card {
  border: 1px solid #eee;
  border-radius: 12px;
  overflow: hidden;
  margin: 8px 0;
  background: #fff;
}
.poi-header {
  padding: 10px 14px 8px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.poi-header::before {
  content: '';
  width: 4px;
  height: 14px;
  background: #1890ff;
  border-radius: 2px;
}
.poi-item {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  gap: 10px;
}
.poi-item + .poi-item {
  border-top: 1px solid #f5f5f5;
}
.poi-rank {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: #f0f0f0;
  color: #999;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.poi-rank.top3 {
  background: #fff0e6;
  color: #fa8c16;
}
.poi-info {
  flex: 1;
  min-width: 0;
}
.poi-name {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
}
.poi-tags {
  display: flex;
  gap: 8px;
  margin-top: 3px;
  font-size: 12px;
  color: #999;
}
.poi-tag.poi-rating {
  color: #f59e0b;
  font-weight: 500;
}
.poi-distance {
  font-size: 12px;
  color: #999;
  flex-shrink: 0;
}
</style>
