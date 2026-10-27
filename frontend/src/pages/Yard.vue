<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, PageHeader, PageHeaderTitle, useColorScheme } from 'frappe-ui'
import Modal from '../components/Modal.vue'
import Field from '../components/Field.vue'
import { YardScene, type Filter, type Snapshot } from '../yard/yard3d'
import { tos } from '../api'
import { useTerminal } from '../composables/useTerminal'
import { useRealtime } from '../composables/useRealtime'

const { selected: terminal } = useTerminal()
const { resolvedColorScheme } = useColorScheme()

const host = ref<HTMLElement>()
let scene: YardScene | null = null
const snap = ref<Snapshot>({ blocks: [], stacks: [], containers: [], lines: [] })
const error = ref('')
const loading = ref(false)

const filter = reactive<Filter>({ line: null, holdsOnly: false, cargo: null })
const hover = ref<{ name: string; x: number; y: number } | null>(null)
const picked = ref<string | null>(null)
const detail = ref<any>(null)

// ---------- data ----------
let inFlight = false
async function load() {
  if (inFlight || !terminal.value) return
  inFlight = true
  loading.value = true
  try {
    const s = (await tos('yard_snapshot', { terminal: terminal.value })) as Snapshot
    snap.value = s
    scene?.setData(s, { ...filter })
    if (picked.value) loadDetail(picked.value)
    error.value = ''
  } catch (e: any) { error.value = e.message } finally { loading.value = false; inFlight = false }
}
let debounce: ReturnType<typeof setTimeout>
const soon = () => { clearTimeout(debounce); debounce = setTimeout(load, 400) }

const { live } = useRealtime(terminal, ['yard_move_started', 'yard_move_done', 'hold_changed', 'gate_status'], () => soon())
let poll: ReturnType<typeof setInterval>
onMounted(() => {
  scene = new YardScene(host.value!, {
    onPick: (n) => { picked.value = n; n ? loadDetail(n) : (detail.value = null) },
    onHover: (h) => (hover.value = h),
  })
  scene.setTheme(resolvedColorScheme.value === 'dark' ? 'dark' : 'light')
  if (snap.value.blocks.length) scene.setData(snap.value, { ...filter })
  load()
  poll = setInterval(() => { if (!live.value && !document.hidden) load() }, 10000)
})
onBeforeUnmount(() => { clearInterval(poll); clearTimeout(debounce); scene?.dispose(); scene = null })
watch(terminal, () => { picked.value = null; detail.value = null; load() })
watch(resolvedColorScheme, (v) => scene?.setTheme(v === 'dark' ? 'dark' : 'light'))
watch(filter, () => scene?.setFilter({ ...filter }), { deep: true })

async function loadDetail(name: string) {
  const c = snap.value.containers.find((x) => x.name === name)
  if (!c?.yard_stack) { detail.value = null; return }
  try { detail.value = await tos('stack_detail', { stack: c.yard_stack }) } catch (e: any) { error.value = e.message }
}

// ---------- derived ----------
const hovered = computed(() => snap.value.containers.find((c) => c.name === hover.value?.name))
const selectedC = computed(() => detail.value?.containers.find((c: any) => c.name === picked.value))
const tiers = computed(() => detail.value?.containers || [])
const lines = computed(() => snap.value.lines)
const holdCount = computed(() => snap.value.containers.filter((c) => c.is_on_hold).length)
const occupancy = computed(() => {
  const used = snap.value.stacks.reduce((n, s) => n + Number(s.tier_count || 0), 0)
  const cap = snap.value.stacks.reduce((n, s) => n + Number(s.max_tier || 0), 0)
  return cap ? Math.round((used / cap) * 100) : 0
})
const lineColour = (name: string) => snap.value.lines.find((l) => l.name === name)?.colour || '#2563EB'
const toggleLine = (name: string) => (filter.line = filter.line === name ? null : name)

// ---------- search ----------
const q = ref('')
const results = ref<any[]>([])
let st: ReturnType<typeof setTimeout>
function onSearch() {
  clearTimeout(st)
  if (q.value.trim().length < 2) { results.value = []; return }
  st = setTimeout(async () => { try { results.value = (await tos('search_container', { q: q.value, terminal: terminal.value })) as any[] } catch { results.value = [] } }, 250)
}
function goTo(name: string) {
  results.value = []; q.value = name
  picked.value = name
  scene?.select(name, true)
  loadDetail(name)
}

// ---------- move order ----------
const mo = reactive({ open: false, move_type: 'Yard Shift', to_stack: '', priority: 'Normal', notes: '', error: '', loading: false, done: '' })
function openMove() { Object.assign(mo, { open: true, move_type: 'Yard Shift', to_stack: '', priority: 'Normal', notes: '', error: '', loading: false, done: '' }) }
async function submitMove() {
  mo.loading = true; mo.error = ''
  try {
    const r = (await act2('create_move_order', { container: picked.value, move_type: mo.move_type, to_stack: mo.to_stack, priority: mo.priority, notes: mo.notes })) as any
    mo.done = `Move order ${r.name} created${r.to_stack ? ' → ' + r.to_stack : ''}.`
  } catch (e: any) { mo.error = e.message } finally { mo.loading = false }
}
const act2 = (name: string, p: Record<string, unknown>) => tos(name, p, { post: true })

const dwell = (c: any) => (c.dwell_days == null ? '' : c.dwell_days + ' d on terminal')
</script>

<template>
  <PageHeader>
    <PageHeaderTitle title="3D Yard" />
    <div class="flex items-center gap-3">
      <Badge :theme="live ? 'green' : 'gray'" :label="live ? 'Live' : 'Updating every 10 s'" />
      <Button icon="lucide-scan" tooltip="Fit all blocks" aria-label="Fit all blocks" @click="scene?.fit()" />
      <Button icon="lucide-refresh-cw" aria-label="Refresh" tooltip="Refresh" :loading="loading" @click="load" />
    </div>
  </PageHeader>

  <div class="relative h-[calc(100vh-3.5rem)] min-h-[520px] w-full overflow-hidden bg-surface-gray-2">
    <div ref="host" class="absolute inset-0" />

    <!-- search + filters -->
    <div class="absolute left-4 top-4 w-52 space-y-2">
      <div class="relative">
        <input v-model="q" class="tos-input shadow-sm" placeholder="Find a container…" aria-label="Find a container" @input="onSearch" />
        <ul v-if="results.length" class="absolute z-10 w-full overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-white shadow-lg">
          <li v-for="r in results" :key="r.name"><button class="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-surface-gray-2" @click="goTo(r.name)"><span class="text-ink-gray-8">{{ r.name }}</span><span class="text-ink-gray-5">{{ r.yard_stack || r.status }}</span></button></li>
        </ul>
      </div>
      <div class="rounded-6 border border-outline-gray-1 bg-surface-white/95 py-3 px-2 shadow-sm backdrop-blur">
        <p class="mb-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Shipping line</p>
        <div class="flex flex-wrap gap-1">
          <button v-for="l in lines" :key="l.name" :aria-pressed="filter.line === l.name" :class="['flex items-center gap-1 rounded-full border px-1 py-0 text-xs', filter.line === l.name ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-7']" @click="toggleLine(l.name)">
            <span class="size-2.5 rounded-full" :style="{ background: lineColour(l.name) }" />{{ l.line_name || l.name }}
          </button>
        </div>
        <div class="mt-3 flex flex-wrap gap-1">
          <button :aria-pressed="!!filter.holdsOnly" :class="['rounded-full border px-1 py-1 text-xs', filter.holdsOnly ? 'border-outline-red-2 bg-surface-red-1 text-ink-red-3' : 'border-outline-gray-2 text-ink-gray-7']" @click="filter.holdsOnly = !filter.holdsOnly">On hold ({{ holdCount }})</button>
          <button v-for="c in ['Full', 'Empty']" :key="c" :aria-pressed="filter.cargo === c" :class="['rounded-full border px-1.5 py-1 text-xs', filter.cargo === c ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-7']" @click="filter.cargo = filter.cargo === c ? null : (c as any)">{{ c }}</button>
        </div>
      </div>
    </div>

    <!-- totals -->
    <div class="absolute bottom-4 left-4 flex gap-4 rounded-6 border border-outline-gray-1 bg-surface-white/95 px-4 py-2 text-sm shadow-sm backdrop-blur">
      <span class="text-ink-gray-6"><b class="text-ink-gray-9 tabular-nums">{{ snap.containers.length }}</b> containers</span>
      <span class="text-ink-gray-6"><b class="text-ink-gray-9 tabular-nums">{{ occupancy }}%</b> full</span>
      <span class="hidden text-ink-gray-5 sm:inline">Drag to rotate · right-drag to pan · scroll to zoom</span>
    </div>

    <ErrorMessage v-if="error" class="absolute bottom-16 left-4 rounded-4 bg-surface-white px-3 py-2" :message="error" />

    <!-- hover tooltip -->
    <div v-if="hover && hovered" class="pointer-events-none absolute z-10 rounded-5 border border-outline-gray-2 bg-surface-white px-2.5 py-1.5 text-xs shadow-lg" :style="{ left: hover.x + 14 + 'px', top: hover.y + 14 + 'px' }">
      <p class="text-sm font-medium text-ink-gray-9">{{ hovered.name }}</p>
      <p class="text-ink-gray-6">{{ hovered.shipping_line }} · {{ hovered.length_ft }} ft · {{ hovered.cargo_status }}</p>
      <p class="text-ink-gray-5">{{ hovered.yard_stack }} · tier {{ hovered.tier }}</p>
    </div>

    <!-- inspector -->
    <aside v-if="picked && detail" class="absolute bottom-4 right-4 top-4 flex w-80 flex-col overflow-hidden rounded-6 border border-outline-gray-1 bg-surface-white shadow-lg">
      <header class="flex items-start justify-between border-b border-outline-gray-1 px-4 py-3">
        <div>
          <p class="text-base-medium text-ink-gray-9">{{ picked }}</p>
          <p class="text-sm text-ink-gray-5">{{ detail.stack?.name }} · {{ tiers.length }} of {{ detail.stack?.max_tier }} tiers</p>
        </div>
        <Button variant="ghost" icon="lucide-x" aria-label="Close" @click="picked = null; detail = null; scene?.select(null)" />
      </header>

      <div v-if="selectedC" class="space-y-1 border-b border-outline-gray-1 px-4 py-3 text-sm">
        <div class="flex justify-between"><span class="text-ink-gray-5">Line</span><span class="text-ink-gray-8">{{ selectedC.shipping_line }}</span></div>
        <div class="flex justify-between"><span class="text-ink-gray-5">Type</span><span class="text-ink-gray-8">{{ selectedC.container_type }} · {{ selectedC.length_ft }} ft</span></div>
        <div class="flex justify-between"><span class="text-ink-gray-5">Cargo</span><span class="text-ink-gray-8">{{ selectedC.cargo_status }}<template v-if="selectedC.gross_weight_kg"> · {{ Math.round(selectedC.gross_weight_kg) }} kg</template></span></div>
        <div class="flex justify-between"><span class="text-ink-gray-5">Dwell</span><span class="text-ink-gray-8">{{ dwell(selectedC) }}</span></div>
        <div v-if="selectedC.free_days_until" class="flex justify-between"><span class="text-ink-gray-5">Free until</span><span class="text-ink-gray-8">{{ selectedC.free_days_until }}</span></div>
        <div v-for="h in selectedC.holds" :key="h.hold_type + h.placed_on" class="mt-2 rounded-4 bg-surface-red-1 px-2 py-1 text-xs text-ink-red-3"><b>{{ h.hold_type }}</b><template v-if="h.reason"> · {{ h.reason }}</template></div>
      </div>

      <p class="px-4 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Stack, top first</p>
      <ul class="flex-1 divide-y divide-outline-gray-1 overflow-y-auto">
        <li v-for="c in tiers" :key="c.name">
          <button :class="['flex w-full items-center gap-2 px-4 py-2 text-left text-sm', c.name === picked ? 'bg-surface-blue-1' : 'hover:bg-surface-gray-1']" @click="goTo(c.name)">
            <span class="w-6 shrink-0 text-xs tabular-nums text-ink-gray-5">T{{ c.tier }}</span>
            <span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ c.name }}</span>
            <Badge v-if="c.is_on_hold" theme="red" label="Hold" />
            <span class="text-xs text-ink-gray-5">{{ c.length_ft }}′</span>
          </button>
        </li>
      </ul>
      <footer class="border-t border-outline-gray-1 p-3"><Button class="w-full" variant="solid" icon-left="lucide-forklift" label="Create move order" @click="openMove" /></footer>
    </aside>
  </div>

  <Modal :open="mo.open" :title="'Move order · ' + picked" :confirm-label="mo.done ? 'Done' : 'Create'" :loading="mo.loading" :error="mo.error" @close="mo.open = false" @confirm="mo.done ? (mo.open = false) : submitMove()">
    <template v-if="mo.done"><p class="text-sm text-ink-gray-8">{{ mo.done }}</p></template>
    <template v-else>
      <div class="grid grid-cols-2 gap-3">
        <Field label="Type"><select v-model="mo.move_type" class="tos-input"><option>Yard Shift</option><option>To Gate Out</option></select></Field>
        <Field label="Priority"><select v-model="mo.priority" class="tos-input"><option>Normal</option><option>High</option><option>Urgent</option></select></Field>
      </div>
      <Field v-if="mo.move_type === 'Yard Shift'" label="Destination stack" hint="Leave empty and the system picks the best free stack."><input v-model="mo.to_stack" class="tos-input" /></Field>
      <Field label="Notes"><textarea v-model="mo.notes" rows="2" class="tos-input" /></Field>
    </template>
  </Modal>
</template>
