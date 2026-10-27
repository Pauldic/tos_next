<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Badge, Button, ErrorMessage, useColorScheme } from 'frappe-ui'
import { opsAct, opsApi } from '../api'
import { useTerminal } from '../composables/useTerminal'
import { usePolling } from '../composables/usePolling'
import { useRealtime } from '../composables/useRealtime'

const { selected, current } = useTerminal()
const { resolvedColorScheme, toggleColorScheme } = useColorScheme()

const board = ref<any>({ user: '', equipment: [], available: [], orders: [], recent: [] })
const error = ref('')
const busy = ref('')
const loaded = ref(false)
const now = ref(Date.now())
const confirming = ref('')
let confirmTimer: ReturnType<typeof setTimeout>
let tick: ReturnType<typeof setInterval>

async function refresh() {
  try {
    board.value = await opsApi('ops_board', { terminal: selected.value })
    loaded.value = true
  } catch (e: any) { error.value = e.message }
}
usePolling(refresh, selected, 8000)
let debounce: ReturnType<typeof setTimeout>
useRealtime(selected, ['yard_move_started', 'yard_move_done'], () => { clearTimeout(debounce); debounce = setTimeout(refresh, 400) })
onMounted(() => { tick = setInterval(() => (now.value = Date.now()), 30000) })
onBeforeUnmount(() => { clearInterval(tick); clearTimeout(confirmTimer); clearTimeout(debounce) })

const myEq = computed(() => board.value.equipment[0])
const active = computed(() => board.value.orders.find((o: any) => o.status === 'In Progress'))
const queued = computed(() => board.value.orders.filter((o: any) => o.status === 'Assigned'))
const freeEq = computed(() => board.value.available)

async function run(key: string, fn: () => Promise<unknown>) {
  busy.value = key
  error.value = ''
  try { await fn(); await refresh() } catch (e: any) { error.value = e.message } finally { busy.value = '' }
}
const start = (o: any) => run('s' + o.name, () => opsAct('move_action', { order: o.name, action: 'start' }))
function complete(o: any) {
  // a second tap within 4 seconds confirms, so a pocket tap cannot finish a move
  if (confirming.value !== o.name) {
    confirming.value = o.name
    clearTimeout(confirmTimer)
    confirmTimer = setTimeout(() => (confirming.value = ''), 4000)
    return
  }
  confirming.value = ''
  run('c' + o.name, () => opsAct('move_action', { order: o.name, action: 'complete' }))
}
const signOn = (e: any) => run('on' + e.name, () => opsAct('sign_on', { equipment: e.name }))
const signOff = (e: any) => run('off' + e.name, () => opsAct('sign_off', { equipment: e.name }))

const prioTheme = (p: string) => ({ Urgent: 'red', High: 'orange', Normal: 'gray' } as Record<string, string>)[p] || 'gray'
const spot = (stack?: string, tier?: number) => (stack ? `${stack}${tier ? ' · T' + tier : ''}` : 'Gate')
const minutes = (since?: string) => (since ? Math.max(0, Math.round((now.value - new Date(since.replace(' ', 'T')).getTime()) / 60000)) : 0)
</script>

<template>
  <div class="mx-auto flex min-h-screen max-w-xl flex-col px-4 pb-10">
    <header class="sticky top-0 z-10 -mx-4 mb-4 flex items-center justify-between border-b border-outline-gray-1 bg-surface-base/95 px-4 py-3 backdrop-blur">
      <div class="min-w-0">
        <h1 class="text-lg-semibold text-ink-gray-9">My moves</h1>
        <p class="truncate text-sm text-ink-gray-5">{{ current?.terminal_name }}<template v-if="board.user"> · {{ board.user }}</template></p>
      </div>
      <div class="flex items-center gap-2">
        <Button icon="lucide-refresh-cw" aria-label="Refresh" @click="refresh" />
        <Button :icon="resolvedColorScheme === 'dark' ? 'lucide-sun' : 'lucide-moon'" aria-label="Switch light and dark mode" @click="toggleColorScheme" />
      </div>
    </header>

    <ErrorMessage v-if="error" class="mb-3 whitespace-pre-line rounded-5 bg-surface-red-1 p-3" :message="error" />

    <!-- machine -->
    <section class="mb-4 rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
      <template v-if="myEq">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-gray-5">Your machine</p>
            <p class="text-xl-semibold text-ink-gray-9">{{ myEq.name }}</p>
            <p class="text-sm text-ink-gray-5">{{ myEq.equipment_type }}<template v-if="myEq.max_lift_tier"> · lifts to tier {{ myEq.max_lift_tier }}</template><template v-if="!myEq.handles_forty"> · 20 ft only</template></p>
          </div>
          <Button label="Sign off" :loading="busy === 'off' + myEq.name" @click="signOff(myEq)" />
        </div>
      </template>
      <template v-else>
        <p class="text-base-medium text-ink-gray-9">Choose your machine</p>
        <p class="mb-3 text-sm text-ink-gray-5">Jobs are assigned to the machine you sign on to.</p>
        <ul class="space-y-2">
          <li v-for="e in freeEq" :key="e.name">
            <button :disabled="['Maintenance', 'Offline'].includes(e.status) || !!busy" class="flex min-h-[52px] w-full items-center justify-between rounded-5 border border-outline-gray-2 px-4 py-2 text-left disabled:opacity-50" @click="signOn(e)">
              <span><span class="text-base-medium text-ink-gray-9">{{ e.name }}</span><span class="block text-sm text-ink-gray-5">{{ e.equipment_type }}</span></span>
              <Badge :theme="e.status === 'Available' ? 'green' : e.status === 'Working' ? 'blue' : 'gray'" :label="e.status" />
            </button>
          </li>
          <li v-if="loaded && !freeEq.length" class="py-2 text-sm text-ink-gray-5">No machines are free right now.</li>
        </ul>
      </template>
    </section>

    <!-- current job -->
    <section v-if="active" class="mb-4 rounded-6 border-2 border-outline-blue-2 bg-surface-white p-4 shadow-sm" aria-label="Current job">
      <div class="flex items-center justify-between">
        <Badge theme="blue" label="In progress" />
        <span class="text-sm text-ink-gray-5">{{ minutes(active.started_at) }} min</span>
      </div>
      <p class="mt-3 break-all text-2xl-semibold tracking-wide text-ink-gray-9">{{ active.container }}</p>
      <p class="text-sm text-ink-gray-5">{{ active.length_ft }} ft · {{ active.move_type }}</p>
      <div class="mt-4 flex items-center gap-3 text-base-medium text-ink-gray-8">
        <span class="flex-1 rounded-4 bg-surface-gray-2 px-3 py-2 text-center">{{ spot(active.from_stack, active.from_tier) }}</span>
        <span class="lucide-arrow-right size-5 text-ink-gray-5" aria-hidden="true" />
        <span class="flex-1 rounded-4 bg-surface-green-1 px-3 py-2 text-center">{{ spot(active.to_stack, active.to_tier) }}</span>
      </div>
      <p v-if="active.notes" class="mt-3 text-sm text-ink-gray-6">{{ active.notes }}</p>
      <Button class="mt-4 !h-14 w-full !text-lg" variant="solid" theme="green" :loading="busy === 'c' + active.name" :label="confirming === active.name ? 'Tap again to confirm' : 'Complete move'" @click="complete(active)" />
    </section>

    <!-- next jobs -->
    <section class="mb-4">
      <h2 class="mb-2 text-base-medium text-ink-gray-9">Up next <span class="text-ink-gray-5">· {{ queued.length }}</span></h2>
      <ul class="space-y-3">
        <li v-for="o in queued" :key="o.name" class="rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="break-all text-lg-semibold text-ink-gray-9">{{ o.container }}</p>
              <p class="text-sm text-ink-gray-5">{{ o.length_ft }} ft · {{ o.move_type }}</p>
            </div>
            <Badge :theme="prioTheme(o.priority)" :label="o.priority" />
          </div>
          <p class="mt-2 text-sm text-ink-gray-7">{{ spot(o.from_stack, o.from_tier) }} → {{ spot(o.to_stack, o.to_tier) }}</p>
          <Button class="mt-3 !h-12 w-full" variant="solid" :disabled="!!active" :loading="busy === 's' + o.name" :label="active ? 'Finish the current move first' : 'Start'" @click="start(o)" />
        </li>
        <li v-if="loaded && !queued.length && !active" class="rounded-6 border border-dashed border-outline-gray-2 p-8 text-center text-sm text-ink-gray-5">
          {{ myEq ? 'No jobs for you right now. This page updates by itself.' : 'Sign on to a machine to receive jobs.' }}
        </li>
      </ul>
    </section>

    <section v-if="board.recent.length">
      <h2 class="mb-2 text-base-medium text-ink-gray-9">Done recently</h2>
      <ul class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-1 bg-surface-white">
        <li v-for="o in board.recent" :key="o.name" class="flex items-center justify-between px-4 py-2.5 text-sm">
          <span class="truncate text-ink-gray-8">{{ o.container }}</span>
          <span class="text-ink-gray-5">{{ spot(o.to_stack, o.to_tier) }}</span>
        </li>
      </ul>
    </section>

    <a href="/tos" class="mt-8 text-center text-sm text-ink-gray-5 underline">Open the full app</a>
  </div>
</template>
