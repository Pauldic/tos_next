<script setup lang="ts">
import { Button, ErrorMessage } from 'frappe-ui'
defineProps<{ open: boolean; title: string; confirmLabel?: string; loading?: boolean; error?: string; wide?: boolean; hideConfirm?: boolean }>()
defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @keydown.esc="$emit('close')" @mousedown.self="$emit('close')">
      <div role="dialog" aria-modal="true" :aria-label="title" :class="['max-h-[90vh] w-full overflow-y-auto rounded-6 border border-outline-gray-1 bg-surface-white p-5 shadow-xl', wide ? 'max-w-2xl' : 'max-w-md']">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-lg-semibold text-ink-gray-9">{{ title }}</h2>
          <Button variant="ghost" icon="lucide-x" aria-label="Close" @click="$emit('close')" />
        </div>
        <div class="space-y-3"><slot /></div>
        <ErrorMessage v-if="error" class="mt-3 whitespace-pre-line" :message="error" />
        <div class="mt-5 flex justify-end gap-2">
          <Button :label="hideConfirm ? 'Close' : 'Cancel'" @click="$emit('close')" />
          <Button v-if="!hideConfirm" variant="solid" :label="confirmLabel || 'Save'" :loading="loading" @click="$emit('confirm')" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
