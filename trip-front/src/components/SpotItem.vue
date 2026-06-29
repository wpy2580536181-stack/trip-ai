<template>
  <div class="spot-item" v-if="data">
    <img v-if="data.imageUrl" :src="data.imageUrl" :alt="data.spot || data.name" class="spot-image"
      @error="onImageError($event)" />
    <div class="spot-name">{{ data.spot || data.name || '待定' }}</div>
    <div class="spot-details" v-if="data.duration || data.ticket || data.transportation">
      <div class="detail-row" v-if="data.duration">
        <span class="detail-icon">🕐</span>
        <span>{{ data.duration }}</span>
      </div>
      <div class="detail-row" v-if="data.ticket">
        <span class="detail-icon">🎫</span>
        <span>{{ data.ticket }}</span>
      </div>
      <div class="detail-row" v-if="data.transportation">
        <span class="detail-icon">🚗</span>
        <span>{{ data.transportation }}</span>
      </div>
    </div>
    <div class="spot-desc" v-if="data.description">{{ data.description }}</div>
  </div>
  <div class="spot-item empty" v-else>
    <div class="empty-placeholder">暂无安排</div>
  </div>
</template>

<script setup lang="ts">
defineProps({
  data: {
    type: Object,
    default: () => ({})
  }
})

const onImageError = (e: Event) => {
  (e.target as HTMLImageElement).style.display = 'none'
}
</script>

<style scoped>
.spot-image {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: 8px;
  margin-bottom: 8px;
  background: var(--bg-secondary);
}

.spot-item {
  padding: 8px 0;
}

.spot-item.empty {
  padding: 16px 0;
}

.spot-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.spot-details {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.detail-icon {
  font-size: 14px;
  line-height: 1;
}

.spot-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.empty-placeholder {
  color: var(--text-secondary);
  font-size: 14px;
  text-align: center;
  padding: 20px 0;
}
</style>
