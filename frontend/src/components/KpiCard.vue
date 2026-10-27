<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
  icon: string
  progress?: number // 0-100, draws a bar
  tone?: 'default' | 'warn'
}>()
</script>

<template>
  <div class="rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
    <div class="flex items-center justify-between">
      <p class="text-sm text-ink-gray-6">{{ label }}</p>
      <span
        :class="[icon, 'size-4', tone === 'warn' ? 'text-ink-amber-3' : 'text-ink-gray-5']"
        aria-hidden="true"
      />
    </div>
    <p class="mt-2 text-2xl-semibold tabular-nums text-ink-gray-9">{{ value }}</p>
    <div v-if="progress !== undefined" class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-gray-3">
      <div
        class="h-full rounded-full bg-surface-blue-3 transition-all"
        :style="{ width: Math.min(100, Math.max(0, progress)) + '%' }"
      />
    </div>
    <p v-if="hint" class="mt-1.5 truncate text-sm text-ink-gray-5">{{ hint }}</p>
  </div>
</template>
