<script setup lang="ts">
import { PageHeader, PageHeaderTitle } from 'frappe-ui'
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <PageHeader><PageHeaderTitle :title="String(route.meta.title || '')" /></PageHeader>
  <div class="mx-auto max-w-[560px] px-4 py-24 text-center">
    <span class="lucide-hammer mx-auto size-8 text-ink-gray-4" aria-hidden="true" />
    <h1 class="mt-4 text-xl-semibold text-ink-gray-9">{{ route.meta.title }} is next</h1>
    <p class="mt-2 text-p-base text-ink-gray-6">The data for this screen is already available from the API. The screen itself is coming in the next batch.</p>
  </div>
</template>
