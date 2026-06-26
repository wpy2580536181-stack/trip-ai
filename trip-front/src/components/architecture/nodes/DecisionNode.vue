<script setup lang="ts">
import { Handle, Position, type NodeProps } from '@vue-flow/core'

interface DecisionNodeData {
  label: string
  sublabel?: string
}

defineProps<NodeProps<DecisionNodeData>>()
</script>

<template>
  <div class="decision-node">
    <svg width="130" height="90" viewBox="0 0 130 90">
      <polygon
        points="65,5 125,45 65,85 5,45"
        fill="#fff2cc"
        stroke="#d6b656"
        stroke-width="1.5"
      />
      <text x="65" y="42" text-anchor="middle" font-size="11" font-weight="600" fill="#5d4a00">
        {{ data.label }}
      </text>
      <text v-if="data.sublabel" x="65" y="56" text-anchor="middle" font-size="9" fill="#7d6a00">
        {{ data.sublabel }}
      </text>
    </svg>
    <Handle type="target" :position="Position.Top" />
    <Handle
      type="source"
      :position="Position.Bottom"
      id="yes"
      :style="{ left: '25%' }"
    />
    <Handle type="source" :position="Position.Right" id="no" />
  </div>
</template>

<style scoped>
.decision-node {
  position: relative;
}
</style>
