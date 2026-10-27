<script setup lang="ts">
import { computed, ref } from 'vue'
import { Badge, Button, ErrorMessage, PageHeader, PageHeaderTitle } from 'frappe-ui'
import KpiCard from '../components/KpiCard.vue'
import { tos } from '../api'
import { useTerminal } from '../composables/useTerminal'
import { usePolling } from '../composables/usePolling'

const { selected, current } = useTerminal()

const kpis = ref<Record<string, number>>({})
const queue = ref<{ open: any[]; recent: any[] }>({ open: [], recent: [] })
const gate = ref<{ lanes: any[]; arrival_queue: any[] }>({ lanes: [], arrival_queue: [] })
const error = ref('')
const loading = ref(false)
const updated = ref('')

async function refresh() {
  loading.value = true
  try {
    const [k, q, g] = await Promise.all([
      tos('kpis', { terminal: selected.value }),
      tos('work_queue', { terminal: selected.value }),
      tos('gate_board', { terminal: selected.value }),
    ])
    kpis.value = k as any
    queue.value = q as any
    gate.value = g as any
    error.value = ''
    updated.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
usePolling(refresh, selected)

const n = (key: string) => Number(kpis.value[key] || 0)
const bookedPct = computed(() => (n('appointment_capacity_today') ? (n('appointments_booked_today') / n('appointment_capacity_today')) * 100 : 0))

const laneTheme = (s: string) => ({ Open: 'green', Busy: 'blue', Closed: 'gray', Fault: 'red' } as Record<string, string>)[s] || 'gray'
const orderTheme = (s: string) => ({ Queued: 'gray', Assigned: 'blue', 'In Progress': 'orange' } as Record<string, string>)[s] || 'gray'
const where = (o: any) => [o.from_stack ? `${o.from_stack}${o.from_tier ? ' T' + o.from_tier : ''}` : 'Gate', o.to_stack ? `${o.to_stack}${o.to_tier ? ' T' + o.to_tier : ''}` : 'Gate'].join(' → ')
</script>

<template>
  <PageHeader>
    <PageHeaderTitle title="Dashboard" />
    <div class="flex items-center gap-3">
      <span v-if="updated" class="text-sm text-ink-gray-5">Updated {{ updated }}</span>
      <Button icon="lucide-refresh-cw" aria-label="Refresh" tooltip="Refresh" :loading="loading" @click="refresh" />
    </div>
  </PageHeader>

  <div class="mx-auto max-w-[1200px] space-y-6 px-4 pb-10 pt-6 sm:px-6">
    <div>
      <h1 class="text-2xl-semibold text-ink-gray-9">{{ current?.terminal_name || 'Terminal' }}</h1>
      <p class="mt-1 text-p-base text-ink-gray-6">Live view of the yard, the gate and today's appointments.</p>
    </div>

    <ErrorMessage v-if="error" :message="error" />

    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard label="Yard occupancy" icon="lucide-layers" :value="n('yard_occupancy_pct') + '%'" :progress="n('yard_occupancy_pct')" :hint="n('containers_on_ground') + ' containers on the ground'" />
      <KpiCard label="Trucks in terminal" icon="lucide-truck" :value="n('trucks_in_terminal')" :hint="n('gate_in_today') + ' in · ' + n('gate_out_today') + ' out today'" />
      <KpiCard label="Moves today" icon="lucide-move" :value="n('moves_today')" :hint="n('open_move_orders') + ' open move orders'" />
      <KpiCard label="Appointments today" icon="lucide-calendar-check" :value="n('appointments_booked_today')" :progress="bookedPct" :hint="'of ' + n('appointment_capacity_today') + ' places'" />
    </div>

    <a
      v-if="n('pending_overrides') > 0"
      href="/app/appointment-override?status=Pending"
      class="flex items-center gap-3 rounded-6 border border-outline-amber-2 bg-surface-amber-1 px-4 py-3 text-ink-amber-3"
    >
      <span class="lucide-shield-alert size-4" aria-hidden="true" />
      <span class="text-base-medium">{{ n('pending_overrides') }} appointment override{{ n('pending_overrides') === 1 ? '' : 's' }} waiting for approval</span>
    </a>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section class="rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
        <header class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-3">
          <h2 class="text-base-medium text-ink-gray-9">Work queue</h2>
          <Badge theme="gray" :label="String(queue.open.length) + ' open'" />
        </header>
        <ul class="divide-y divide-outline-gray-1">
          <li v-for="o in queue.open" :key="o.name" class="flex items-center gap-3 px-4 py-2.5">
            <div class="min-w-0 flex-1">
              <p class="truncate text-base-medium text-ink-gray-8">{{ o.container }} <span class="text-ink-gray-5">· {{ o.move_type }}</span></p>
              <p class="truncate text-sm text-ink-gray-5">{{ where(o) }}</p>
            </div>
            <Badge :theme="orderTheme(o.status)" :label="o.status" />
          </li>
          <li v-if="!queue.open.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">Nothing waiting. The yard is quiet.</li>
        </ul>
      </section>

      <section class="rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
        <header class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-3">
          <h2 class="text-base-medium text-ink-gray-9">Gate lanes</h2>
          <Badge theme="gray" :label="String(gate.arrival_queue.length) + ' arriving soon'" />
        </header>
        <ul class="divide-y divide-outline-gray-1">
          <li v-for="l in gate.lanes" :key="l.name" class="flex items-center gap-3 px-4 py-2.5">
            <span :class="[l.direction === 'In' ? 'lucide-log-in' : 'lucide-log-out', 'size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <p class="text-base-medium text-ink-gray-8">{{ l.lane_code }}</p>
              <p class="truncate text-sm text-ink-gray-5">
                {{ l.transaction ? (l.transaction.truck || 'Truck') + ' · ' + (l.transaction.container || 'no container yet') : 'No truck' }}
              </p>
            </div>
            <Badge :theme="laneTheme(l.status)" :label="l.status" />
          </li>
          <li v-if="!gate.lanes.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">No gate lanes set up.</li>
        </ul>
      </section>
    </div>
  </div>
</template>
