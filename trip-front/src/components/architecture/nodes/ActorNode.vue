<script setup lang="ts">
import { Handle, Position, type NodeProps } from '@vue-flow/core'

interface ActorNodeData {
  label: string
  sublabel?: string
}

defineProps<NodeProps<ActorNodeData>>()
</script>

<template>
  <div class="actor-node" style="background: #fff2cc; border: 1.5px solid #d6b656">
    <div class="label">{{ data.label }}</div>
    <div v-if="data.sublabel" class="sublabel">{{ data.sublabel }}</div>
    <Handle type="target" :position="Position.Top" />
    <Handle type="source" :position="Position.Bottom" />
  </div>
</template>

<style scoped>
.actor-node {
  padding: 10px 14px;
  border-radius: 4px;
  min-width: 110px;
  text-align: center;
  font-size: 12px;
  position: relative;
}
.label {
  font-weight: 600;
  color: #5d4a00;
  line-height: 1.3;
}
.sublabel {
  font-size: 10px;
  color: #7d6a00;
  margin-top: 3px;
}
</style>
