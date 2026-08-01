<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  fields: {
    key: string
    label: string
    field_type: string
    required?: boolean
    placeholder?: string
    options?: string[]
  }[]
  title?: string
  submitLabel?: string
  cancelLabel?: string
}>()

const emit = defineEmits<{
  (e: 'submit', values: Record<string, any>): void
  (e: 'cancel'): void
}>()

const formValues = ref<Record<string, any>>({})

const handleSubmit = () => {
  emit('submit', { ...formValues.value })
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<template>
  <div class="clarify-card">
    <div class="clarify-header">{{ title || '请补充以下信息' }}</div>
    <div class="clarify-body">
      <div v-for="field in fields" :key="field.key" class="clarify-field">
        <label class="clarify-label">
          {{ field.label }}
          <span v-if="field.required" class="clarify-required">*</span>
        </label>
        <n-select
          v-if="field.field_type === 'select'"
          v-model:value="formValues[field.key]"
          :options="(field.options || []).map(o => ({ label: o, value: o }))"
          :placeholder="field.placeholder || `请选择${field.label}`"
          clearable
        />
        <n-input
          v-else
          v-model:value="formValues[field.key]"
          :type="field.field_type"
          :placeholder="field.placeholder || `请输入${field.label}`"
        />
      </div>
    </div>
    <div class="clarify-actions">
      <n-button size="small" @click="handleCancel">{{ cancelLabel || '取消' }}</n-button>
      <n-button size="small" type="primary" @click="handleSubmit">{{ submitLabel || '确定' }}</n-button>
    </div>
  </div>
</template>

<style scoped>
.clarify-card {
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  overflow: hidden;
  margin: 8px 0;
  background: #fff;
}
.clarify-header {
  padding: 10px 14px 8px;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  border-bottom: 1px solid #f0f0f0;
}
.clarify-body {
  padding: 12px 14px;
}
.clarify-field {
  margin-bottom: 12px;
}
.clarify-label {
  display: block;
  font-size: 13px;
  color: #666;
  margin-bottom: 6px;
}
.clarify-required {
  color: #f56c6c;
  margin-left: 2px;
}
.clarify-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}
</style>
