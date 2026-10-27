<script setup lang="ts">
import { ref } from 'vue'
import { tos } from '../api'
import { useTerminal } from '../composables/useTerminal'

const model = defineModel<string>({ default: '' })
const { selected } = useTerminal()
const options = ref<string[]>([])
const id = 'ctr-' + Math.random().toString(36).slice(2, 8)
let t: ReturnType<typeof setTimeout>

function onInput() {
  clearTimeout(t)
  t = setTimeout(async () => {
    try {
      const r = (await tos('search_container', { q: model.value, terminal: selected.value })) as any[]
      options.value = r.map((c) => c.name)
    } catch { options.value = [] }
  }, 250)
}
</script>

<template>
  <input v-model="model" class="tos-input" :list="id" placeholder="e.g. MSCU1234567" autocomplete="off" @input="onInput" />
  <datalist :id="id"><option v-for="o in options" :key="o" :value="o" /></datalist>
</template>
