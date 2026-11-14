<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, PageHeader, PageHeaderTitle } from 'frappe-ui'
import { containerApi } from '../api_container'
import { useTerminal } from '../composables/useTerminal'
import { usePolling } from '../composables/usePolling'

const router = useRouter()
const { selected } = useTerminal()
const rows = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const PAGE = 100
const page = ref(0)
const f = reactive({ search: '', transit_state: '', category: '', full_empty: '', is_hazmat: '', is_reefer: '', is_on_hold: '' })

async function refresh() {
  if (!selected.value) return
  loading.value = true
  try {
    const filters: Record<string, any> = {}
    for (const [k, v] of Object.entries(f)) if (k !== 'search' && v !== '') filters[k] = Number(v) || v
    rows.value = (await containerApi('container_list', { terminal: selected.value, filters, search: f.search, limit: PAGE, start: page.value * PAGE })) as any[]
    error.value = ''
  } catch (e: any) { error.value = e.message } finally { loading.value = false }
}
usePolling(refresh, selected, 30000)
let t: ReturnType<typeof setTimeout>
watch(f, () => { clearTimeout(t); t = setTimeout(() => { page.value = 0; refresh() }, 300) })
watch(page, refresh)

const stateTheme = (s: string) => ({ Yard: 'green', 'Awaiting Slot': 'orange', Expected: 'blue', 'On Vessel': 'gray', 'Gated Out': 'gray' } as Record<string, string>)[s] || 'gray'
const date = (d?: string) => (d ? d.slice(0, 16) : '')
const COLS = ['Container', 'Dwell', 'ISO', 'Category', 'F/E', 'Transit', 'Position', 'Reefer', 'Hazard', 'Seal', 'B/L', 'Carrier', 'Time in']
</script>

<template>
  <div class="flex h-full flex-col">
    <PageHeader><PageHeaderTitle>Containers</PageHeaderTitle></PageHeader>
    <div class="flex flex-wrap items-center gap-2 border-b px-5 py-3">
      <input v-model="f.search" class="tos-input !w-60" placeholder="Search number, B/L or booking" />
      <select v-model="f.transit_state" class="tos-input !w-40"><option value="">Any state</option><option v-for="s in ['Expected','Awaiting Slot','Yard','On Vessel','Gated Out']" :key="s">{{ s }}</option></select>
      <select v-model="f.category" class="tos-input !w-40"><option value="">Any category</option><option v-for="s in ['Import','Export','Transshipment','Storage']" :key="s">{{ s }}</option></select>
      <select v-model="f.full_empty" class="tos-input !w-28"><option value="">F/E</option><option v-for="s in ['FCL','LCL','MT']" :key="s">{{ s }}</option></select>
      <select v-model="f.is_hazmat" class="tos-input !w-32"><option value="">Hazard</option><option value="1">Hazmat</option><option value="0">Not hazmat</option></select>
      <select v-model="f.is_reefer" class="tos-input !w-32"><option value="">Reefer</option><option value="1">Reefer</option><option value="0">Not reefer</option></select>
      <select v-model="f.is_on_hold" class="tos-input !w-32"><option value="">Holds</option><option value="1">On hold</option><option value="0">No hold</option></select>
      <span v-if="loading" class="text-xs text-ink-gray-5">Loading…</span>
    </div>
    <p v-if="error" class="px-5 py-2 text-sm text-ink-red-4">{{ error }}</p>
    <div class="flex-1 overflow-auto">
      <table class="w-full text-sm">
        <thead class="sticky top-0 bg-surface-gray-1 text-left text-xs text-ink-gray-6"><tr><th v-for="c in COLS" :key="c" class="whitespace-nowrap px-3 py-2 font-medium">{{ c }}</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.name" class="cursor-pointer border-b hover:bg-surface-gray-1" @click="router.push('/containers/' + encodeURIComponent(r.name))">
            <td class="whitespace-nowrap px-3 py-2 font-medium">{{ r.name }}<Badge v-if="r.is_on_hold" class="ml-2" theme="red" label="Hold" /></td>
            <td class="px-3 py-2">{{ r.dwell_days ?? '' }}</td>
            <td class="px-3 py-2">{{ r.container_type }}</td>
            <td class="px-3 py-2">{{ r.category }}</td>
            <td class="px-3 py-2">{{ r.full_empty }}</td>
            <td class="px-3 py-2"><Badge :theme="stateTheme(r.transit_state)" :label="r.transit_state" /></td>
            <td class="whitespace-nowrap px-3 py-2">
              <router-link v-if="r.position" :to="{ path: '/yard', query: { container: r.name } }" class="text-ink-blue-3 underline" title="Show in the 3D yard" @click.stop>{{ r.position }}</router-link>
            </td>
            <td class="px-3 py-2">{{ r.reefer_temp }}</td>
            <td class="px-3 py-2">{{ r.is_hazmat ? r.imdg_summary || 'Yes' : '' }}</td>
            <td class="px-3 py-2">{{ r.seal_verified ? 'Verified' : '' }}</td>
            <td class="px-3 py-2">{{ r.bill_of_lading }}</td>
            <td class="px-3 py-2">{{ r.shipping_line }}</td>
            <td class="whitespace-nowrap px-3 py-2">{{ date(r.arrived_on) }}</td>
          </tr>
          <tr v-if="!rows.length && !loading"><td :colspan="COLS.length" class="px-3 py-10 text-center text-ink-gray-5">No containers match.</td></tr>
        </tbody>
      </table>
    </div>
    <div class="flex items-center justify-end gap-3 border-t px-5 py-2 text-sm">
      <button class="tos-input !w-auto" :disabled="page === 0" @click="page--">Previous</button>
      <span>Page {{ page + 1 }}</span>
      <button class="tos-input !w-auto" :disabled="rows.length < PAGE" @click="page++">Next</button>
    </div>
  </div>
</template>
