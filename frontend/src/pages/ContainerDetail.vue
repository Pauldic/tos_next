<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, PageHeader, PageHeaderTitle } from 'frappe-ui'
import { containerApi } from '../api_container'

const route = useRoute()
const name = computed(() => decodeURIComponent(String(route.params.name)))
const c = ref<any>(null)
const h = ref<any>({ moves: [], holds: [], gate: [], events: [], timeline: [] })
const tab = ref<'details' | 'moves' | 'events' | 'gate' | 'holds'>('details')
const error = ref('')

async function load() {
  try {
    const [d, hist] = await Promise.all([containerApi('container_detail', { container: name.value }), containerApi('container_history', { container: name.value })])
    c.value = d; h.value = hist; error.value = ''
  } catch (e: any) { error.value = e.message }
}
watch(name, load, { immediate: true })

const TABS = computed(() => [
  ['details', 'Details'], ['moves', `Moves (${h.value.moves.length})`], ['events', `Events (${h.value.events.length})`],
  ['gate', `Gate (${h.value.gate.length})`], ['holds', `Holds (${h.value.holds.length})`],
] as [typeof tab.value, string][])
const dt = (d?: string) => (d ? d.slice(0, 16) : '')
const hazards = computed(() => (c.value?.hazards || []).map((x: any) => `Class ${x.imdg_class}${x.un_number ? ' · UN' + x.un_number : ''}${x.proper_shipping_name ? ' · ' + x.proper_shipping_name : ''}`))
const groups = computed(() => {
  const x = c.value; if (!x) return []
  const stows = [1, 2, 3, 4, 5].map((i) => x['special_stow_' + i]).filter(Boolean).join(', ')
  return [
    ['Identity', [['Container', x.name], ['ISO / type', x.container_type], ['Category', x.category], ['F/E', x.full_empty], ['Group code', x.group_code], ['Carrier line', x.shipping_line], ['Line', x.line], ['Terminal line', x.terminal_line], ['Consignee', x.consignee], ['Remarks', x.remarks]]],
    ['Location', [['Transit state', x.transit_state], ['Status', x.status], ['Position', x.position], ['Planned position', x.planned_position], ['Time in', dt(x.arrived_on)], ['Dwell days', x.dwell_days]]],
    ['Cargo', [['Seal', x.seal_no], ['Seal verified', x.seal_verified ? `Yes${x.seal_verified_by ? ' by ' + x.seal_verified_by : ''}` : 'No'], ['Gross weight (kg)', x.gross_weight_kg], ['Reefer temp (°C)', x.reefer_set_temp_c], ['Reefer plugged', x.reefer_plugged ? 'Yes' : ''], ['Hazard (IMDG)', hazards.value.join('; ')], ['Special stow', stows]]],
    ['Vessels', [['Inbound', [x.ib_vessel_name, x.ib_vessel_voyage].filter(Boolean).join(' · ')], ['Inbound class', x.ib_vessel_class], ['Outbound', [x.ob_vessel_name, x.ob_vessel_voyage].filter(Boolean).join(' · ')], ['Outbound class', x.ob_vessel_class], ['POL', x.pol], ['POD', x.pod], ['Destination', x.destination], ['Place of delivery', x.place_of_delivery]]],
    ['Commercial and billing', [['B/L reference', x.bill_of_lading], ['Booking', x.booking_ref], ['Free days until', x.free_days_until], ['Storage paid', x.storage_paid_date], ['Reefer storage paid', x.reefer_storage_paid], ['Line storage paid', x.line_storage_paid]]],
  ] as [string, [string, any][]][]
})
</script>

<template>
  <div class="flex h-full flex-col">
    <PageHeader>
      <PageHeaderTitle>{{ name }}</PageHeaderTitle>
      <div v-if="c" class="flex items-center gap-2">
        <Badge theme="gray" :label="c.transit_state" /><Badge v-if="c.is_on_hold" theme="red" label="On hold" />
        <router-link v-if="c.yard_stack" :to="{ path: '/yard', query: { container: c.name } }" class="text-sm text-ink-blue-3 underline">Show in 3D yard ({{ c.position }})</router-link>
        <router-link to="/containers" class="text-sm text-ink-gray-6 underline">All containers</router-link>
      </div>
    </PageHeader>
    <p v-if="error" class="px-5 py-3 text-sm text-ink-red-4">{{ error }}</p>
    <div class="flex gap-1 border-b px-5">
      <button v-for="[k, l] in TABS" :key="k" class="px-3 py-2 text-sm" :class="tab === k ? 'border-b-2 border-ink-gray-9 font-medium' : 'text-ink-gray-6'" @click="tab = k">{{ l }}</button>
    </div>
    <div class="flex-1 overflow-auto p-5 text-sm">
      <div v-if="tab === 'details' && c" class="grid gap-6 md:grid-cols-2">
        <section v-for="[title, items] in groups" :key="title">
          <h3 class="mb-2 font-medium">{{ title }}</h3>
          <dl class="grid grid-cols-[10rem_1fr] gap-y-1"><template v-for="[k, v] in items" :key="k"><dt class="text-ink-gray-5">{{ k }}</dt><dd>{{ v ?? '' }}</dd></template></dl>
        </section>
      </div>
      <table v-else-if="tab === 'moves'" class="w-full"><thead class="text-left text-xs text-ink-gray-6"><tr><th class="py-1">Time</th><th>Move</th><th>From</th><th>To</th><th>By</th><th>Equipment</th></tr></thead>
        <tbody><tr v-for="m in h.moves" :key="m.name" class="border-t"><td class="py-1.5">{{ dt(m.timestamp) }}</td><td>{{ m.movement_type }}</td><td>{{ m.from_stack }} {{ m.from_tier }}</td><td>{{ m.to_stack }} {{ m.to_tier }}</td><td>{{ m.performed_by }}</td><td>{{ m.equipment }}</td></tr></tbody></table>
      <ul v-else-if="tab === 'events'" class="space-y-2">
        <li v-for="e in h.timeline" :key="e.kind + e.ref + e.title + e.time" class="flex gap-3 border-t pt-2"><span class="w-36 shrink-0 text-ink-gray-5">{{ dt(e.time) }}</span><Badge theme="gray" :label="e.kind" /><span><b>{{ e.title }}</b> {{ e.detail }}<span v-if="e.by" class="text-ink-gray-5"> · {{ e.by }}</span></span></li>
      </ul>
      <div v-else-if="tab === 'gate'" class="space-y-4">
        <div v-for="g in h.gate" :key="g.name" class="rounded-lg border p-3">
          <div class="font-medium">{{ g.name }} · {{ g.direction }} · {{ g.move_type }} <Badge theme="gray" :label="g.status" /></div>
          <div class="text-ink-gray-6">{{ dt(g.entered_at) }} → {{ dt(g.exited_at) }} · {{ g.carrier }} · {{ g.truck }} · {{ g.driver }} <span v-if="g.damage_found" class="text-ink-red-4">· Damage: {{ g.damage_notes }}</span></div>
          <ul class="mt-2"><li v-for="s in g.steps" :key="s.step">{{ s.step }}: {{ s.result }} <span class="text-ink-gray-5">{{ s.checked_by }} {{ dt(s.checked_on) }} {{ s.remarks }}</span></li></ul>
        </div>
        <p v-if="!h.gate.length" class="text-ink-gray-5">No gate transactions.</p>
      </div>
      <div v-else-if="tab === 'holds'" class="space-y-3">
        <div v-for="x in h.holds" :key="x.name" class="rounded-lg border p-3">
          <div class="font-medium">{{ x.hold_type }} <Badge :theme="x.status === 'Active' ? 'red' : 'gray'" :label="x.status" /></div>
          <div>{{ x.reason }}</div>
          <div class="text-ink-gray-6">Placed {{ dt(x.placed_on) }} by {{ x.placed_by }}<span v-if="x.released_on"> · Released {{ dt(x.released_on) }} by {{ x.released_by }} {{ x.release_note }}</span></div>
        </div>
        <p v-if="!h.holds.length" class="text-ink-gray-5">No holds.</p>
      </div>
    </div>
  </div>
</template>
