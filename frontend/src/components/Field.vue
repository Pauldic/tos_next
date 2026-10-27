<script setup lang="ts">
defineProps<{ label: string; hint?: string }>()
</script>

<template>
  <label class="block">
    <span class="mb-1 block text-sm text-ink-gray-6">{{ label }}</span>
    <slot />
    <span v-if="hint" class="mt-1 block text-xs text-ink-gray-5">{{ hint }}</span>
  </label>
</template>

<style>
.tos-input {
  width: 100%;
  border-radius: 0.5rem;
  border: 1px solid var(--outline-gray-2, #d1d5db);
  background: var(--surface-white, #fff);
  padding: 0.4rem 0.6rem;
  font-size: 0.875rem;
  color: var(--ink-gray-8, #111827);
}
.tos-input:focus { outline: 2px solid var(--outline-gray-4, #60a5fa); outline-offset: 0; }
</style>
