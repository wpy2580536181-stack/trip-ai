<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core'

interface GroupNodeData {
  label: string
  items: string[]
}

defineProps<NodeProps<GroupNodeData>>()
</script>

<template>
  <div class="group-node" style="background: #f5f5f5; border: 1.5px dashed #999">
    <div class="label">{{ data.label }}</div>
    <div class="grid">
      <div v-for="item in data.items" :key="item" class="grid-item">
        {{ item }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.group-node {
  padding: 10px;
  border-radius: 8px;
  min-width: 220px;
  font-size: 11px;
  position: relative;
}
.label {
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
  text-align: center;
  font-size: 12px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.grid-item {
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 6px 8px;
  text-align: center;
  font-size: 10px;
  color: #555;
}
</style>
