<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage } from 'frappe-ui'
import Modal from './Modal.vue'
import Field from './Field.vue'
import { slotApi, slotAct } from '../api_slots'

// Planner tools for the time slots: change the capacity of several slots at once, block and unblock them, add a slot,
// copy a day. Nothing is cancelled silently: a slot that already has trucks booked is reported, not changed, unless
// the planner says so.
const props = defineProps<{ terminal: string; date: string }>()
const emit = defineEmits<{ changed: [] }>()

const slots = ref<any[]>([])
const picked = ref<string[]>([])
const error = ref('')
const busy = ref(false)
const notice = ref('')

async function load() {
  if (!props.terminal) return
  try { slots.value = (await slotApi('slots_for_day', { date: props.date, terminal: props.terminal })) as any[]; picked.value = picked.value.filter((n) => slots.value.some((s) => s.name === n)); error.value = '' }
  catch (e: any) { error.value = e.message }
}
watch(() => [props.terminal, props.date], load, { immediate: true })

const hm = (t?: string) => (t || '').slice(0, 5)
const allPicked = computed(() => slots.value.length > 0 && picked.value.length === slots.value.length)
const toggleAll = () => (picked.value = allPicked.value ? [] : slots.value.map((s) => s.name))
const pickBy = (fn: (s: any) => boolean) => (picked.value = slots.value.filter(fn).map((s) => s.name))

// ---- bulk change ----
const ACTIONS = [
  { v: 'set_capacity', l: 'Set capacity to' },
  { v: 'add_capacity', l: 'Add to capacity (use a minus to take away)' },
  { v: 'block', l: 'Block (close) the slots' },
  { v: 'unblock', l: 'Unblock (reopen) the slots' },
  { v: 'set_scope', l: 'Change which jobs they take' },
]
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const f = reactive({ action: 'set_capacity', capacity: '', reason: '', scope: 'All', allow_booked: false, mode: 'selected', date_from: props.date, date_to: props.date, time_from: '', time_to: '', weekdays: [] as number[] })
watch(() => props.date, (d) => { f.date_from = d; if (f.date_to < d) f.date_to = d })
const needsNumber = computed(() => f.action === 'set_capacity' || f.action === 'add_capacity')
const outcome = ref<any>(null)

function payload(preview: boolean) {
  const p: Record<string, unknown> = { action: f.action, terminal: props.terminal, preview: preview ? 1 : 0, allow_booked: f.allow_booked ? 1 : 0 }
  if (needsNumber.value) p.capacity = f.capacity
  if (f.action === 'block') p.reason = f.reason
  if (f.action === 'set_scope') p.move_types = f.scope
  if (f.mode === 'selected') p.slots = picked.value
  else Object.assign(p, { date_from: f.date_from, date_to: f.date_to, time_from: f.time_from, time_to: f.time_to, weekdays: f.weekdays })
  return p
}
async function run(preview: boolean) {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    outcome.value = await slotAct('bulk_update', payload(preview))
    if (!preview) {
      notice.value = `${outcome.value.changed.length} slot${outcome.value.changed.length === 1 ? '' : 's'} changed.` + (outcome.value.skipped.length ? ` ${outcome.value.skipped.length} left as they were.` : '')
      if (outcome.value.booked_in_blocked_slots) notice.value += ` ${outcome.value.booked_in_blocked_slots} booked truck(s) are in blocked slots: their appointments are untouched, so contact those carriers.`
      await load(); emit('changed')
    }
  } catch (e: any) { error.value = e.message; outcome.value = null } finally { busy.value = false }
}
const canRun = computed(() => (f.mode === 'selected' ? picked.value.length > 0 : !!(f.date_from && f.date_to)) && (!needsNumber.value || f.capacity !== '') && (f.action !== 'block' || f.reason.trim()))
watch(f, () => { outcome.value = null; notice.value = '' }, { deep: true })
watch(picked, () => { outcome.value = null })

// ---- add a slot ----
const add = reactive({ open: false, from: '', to: '', capacity: 5, scope: 'All', error: '', loading: false })
async function submitAdd() {
  add.loading = true; add.error = ''
  try { await slotAct('add_slot', { date: props.date, time_from: add.from, time_to: add.to, capacity: add.capacity, move_types: add.scope, terminal: props.terminal }); add.open = false; await load(); emit('changed') }
  catch (e: any) { add.error = e.message } finally { add.loading = false }
}

// ---- copy this day ----
const copy = reactive({ open: false, from: props.date, to: props.date, weekdays: [0, 1, 2, 3, 4] as number[], error: '', loading: false, result: '' })
function openCopy() { const d = new Date(props.date + 'T00:00:00'); d.setDate(d.getDate() + 1); const nxt = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); Object.assign(copy, { open: true, from: nxt, to: nxt, error: '', result: '' }) }
function copyDays(): string[] {
  const out: string[] = []
  for (let d = new Date(copy.from + 'T00:00:00'); d <= new Date(copy.to + 'T00:00:00') && out.length < 31; d.setDate(d.getDate() + 1)) {
    if (copy.weekdays.includes((d.getDay() + 6) % 7)) out.push(new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10))
  }
  return out
}
async function submitCopy() {
  copy.loading = true; copy.error = ''; copy.result = ''
  try {
    const days = copyDays()
    if (!days.length) throw new Error('No days match the range and weekdays you chose.')
    const r = (await slotAct('copy_day', { from_date: props.date, to_dates: days, terminal: props.terminal })) as any
    copy.result = `${r.created} slot${r.created === 1 ? '' : 's'} created on ${days.length} day${days.length === 1 ? '' : 's'}. ${r.already_there} already existed and were kept.`
    emit('changed')
  } catch (e: any) { copy.error = e.message } finally { copy.loading = false }
}
const toggleDay = (list: number[], d: number) => { const i = list.indexOf(d); i < 0 ? list.push(d) : list.splice(i, 1) }

async function remove(s: any) {
  if (!confirm(`Delete the ${hm(s.start_time)} slot? It has no bookings.`)) return
  try { await slotAct('delete_slot', { name: s.name }); await load(); emit('changed') } catch (e: any) { error.value = e.message }
}
</script>

<template>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
    <section class="rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
      <header class="flex flex-wrap items-center justify-between gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h2 class="text-base-medium text-ink-gray-9">Slots on {{ date }}</h2>
        <div class="flex flex-wrap gap-2">
          <Button size="sm" label="Select all" @click="toggleAll" />
          <Button size="sm" label="Select morning" @click="pickBy((s) => hm(s.start_time) < '12:00')" />
          <Button size="sm" label="Select afternoon" @click="pickBy((s) => hm(s.start_time) >= '12:00')" />
          <Button size="sm" icon-left="lucide-plus" label="Add slot" @click="Object.assign(add, { open: true, from: '', to: '', error: '' })" />
          <Button size="sm" icon-left="lucide-copy" label="Copy this day" :disabled="!slots.length" @click="openCopy" />
        </div>
      </header>
      <ErrorMessage v-if="error" class="px-4 pt-3" :message="error" />
      <ul class="divide-y divide-outline-gray-1">
        <li v-for="s in slots" :key="s.name" class="flex items-center gap-3 px-4 py-2.5">
          <input v-model="picked" type="checkbox" :value="s.name" :aria-label="'Select ' + hm(s.start_time)" />
          <span class="w-28 text-base-medium tabular-nums text-ink-gray-8">{{ hm(s.start_time) }}–{{ hm(s.end_time) }}</span>
          <span class="w-20 text-sm tabular-nums text-ink-gray-6">{{ s.booked }} / {{ s.capacity }}</span>
          <Badge theme="gray" :label="s.move_types === 'All' ? 'In and out' : s.move_types" />
          <Badge v-if="s.is_closed" theme="red" :label="'Blocked' + (s.closed_reason ? ': ' + s.closed_reason : '')" />
          <span class="flex-1" />
          <Button v-if="!s.booked" variant="ghost" icon="lucide-trash-2" aria-label="Delete this slot" @click="remove(s)" />
        </li>
        <li v-if="!slots.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">No slots on this day. Add one, or copy another day.</li>
      </ul>
    </section>

    <section class="h-fit space-y-3 rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
      <h2 class="text-base-medium text-ink-gray-9">Change slots</h2>
      <Field label="Apply to">
        <select v-model="f.mode" class="tos-input"><option value="selected">The {{ picked.length }} slot{{ picked.length === 1 ? '' : 's' }} ticked on the left</option><option value="range">A range of days and times</option></select>
      </Field>
      <template v-if="f.mode === 'range'">
        <div class="grid grid-cols-2 gap-2"><Field label="From day"><input v-model="f.date_from" type="date" class="tos-input" /></Field><Field label="To day"><input v-model="f.date_to" type="date" class="tos-input" /></Field></div>
        <div class="grid grid-cols-2 gap-2"><Field label="From time (optional)"><input v-model="f.time_from" type="time" class="tos-input" /></Field><Field label="Until (optional)"><input v-model="f.time_to" type="time" class="tos-input" /></Field></div>
        <div><p class="mb-1 text-sm text-ink-gray-6">Only on these weekdays (none ticked = all)</p>
          <div class="flex flex-wrap gap-1"><button v-for="(d, i) in DAYS" :key="d" :aria-pressed="f.weekdays.includes(i)" :class="['rounded-4 border px-2 py-1 text-xs', f.weekdays.includes(i) ? 'border-outline-blue-2 bg-surface-blue-1' : 'border-outline-gray-2']" @click="toggleDay(f.weekdays, i)">{{ d }}</button></div>
        </div>
      </template>
      <Field label="Do this"><select v-model="f.action" class="tos-input"><option v-for="a in ACTIONS" :key="a.v" :value="a.v">{{ a.l }}</option></select></Field>
      <Field v-if="needsNumber" :label="f.action === 'set_capacity' ? 'Trucks per slot' : 'Trucks to add (or take away)'"><input v-model="f.capacity" type="number" class="tos-input" /></Field>
      <Field v-if="f.action === 'block'" label="Reason" hint="Shown to planners. For example: crane breakdown, public holiday."><input v-model="f.reason" class="tos-input" /></Field>
      <Field v-if="f.action === 'set_scope'" label="Jobs"><select v-model="f.scope" class="tos-input"><option value="All">Receive and deliver</option><option value="Gate In">Receive (Gate In) only</option><option value="Gate Out">Deliver (Gate Out) only</option></select></Field>
      <label v-if="f.action === 'block'" class="flex items-start gap-2 text-sm text-ink-gray-7"><input v-model="f.allow_booked" type="checkbox" class="mt-1" />Block even if trucks are already booked (their appointments stay; you must contact the carriers)</label>
      <div class="flex gap-2">
        <Button label="Preview" :disabled="!canRun" :loading="busy" @click="run(true)" />
        <Button variant="solid" label="Apply" :disabled="!canRun || (outcome && outcome.preview && !outcome.changed.length)" :loading="busy" @click="run(false)" />
      </div>
      <div v-if="outcome" class="rounded-5 bg-surface-gray-1 p-3 text-sm">
        <p class="font-medium text-ink-gray-8">{{ outcome.preview ? 'Would change' : 'Changed' }} {{ outcome.changed.length }} slot{{ outcome.changed.length === 1 ? '' : 's' }}<span v-if="outcome.skipped.length">, leave {{ outcome.skipped.length }}</span></p>
        <ul v-if="outcome.skipped.length" class="mt-1 max-h-40 list-disc space-y-0.5 overflow-y-auto pl-5 text-ink-amber-3"><li v-for="k in outcome.skipped" :key="k.slot">{{ k.label }}: {{ k.reason }}</li></ul>
      </div>
      <p v-if="notice" class="rounded-5 bg-surface-green-1 p-3 text-sm text-ink-green-3">{{ notice }}</p>
    </section>
  </div>

  <Modal :open="add.open" title="Add a slot" :loading="add.loading" :error="add.error" confirm-label="Add slot" @close="add.open = false" @confirm="submitAdd">
    <p class="text-sm text-ink-gray-6">On {{ date }}.</p>
    <div class="grid grid-cols-2 gap-3"><Field label="From"><input v-model="add.from" type="time" class="tos-input" /></Field><Field label="To"><input v-model="add.to" type="time" class="tos-input" /></Field></div>
    <div class="grid grid-cols-2 gap-3">
      <Field label="Trucks"><input v-model.number="add.capacity" type="number" min="0" class="tos-input" /></Field>
      <Field label="Jobs"><select v-model="add.scope" class="tos-input"><option value="All">Receive and deliver</option><option value="Gate In">Receive (Gate In) only</option><option value="Gate Out">Deliver (Gate Out) only</option></select></Field>
    </div>
  </Modal>

  <Modal :open="copy.open" title="Copy this day's slots" :loading="copy.loading" :error="copy.error" confirm-label="Copy" @close="copy.open = false" @confirm="submitCopy">
    <p class="text-sm text-ink-gray-6">Copies the times, capacity, job scope and blocked state of {{ date }}. A day that already has a slot at the same time keeps its own.</p>
    <div class="grid grid-cols-2 gap-3"><Field label="From day"><input v-model="copy.from" type="date" class="tos-input" /></Field><Field label="To day"><input v-model="copy.to" type="date" class="tos-input" /></Field></div>
    <div><p class="mb-1 text-sm text-ink-gray-6">On these weekdays</p>
      <div class="flex flex-wrap gap-1"><button v-for="(d, i) in DAYS" :key="d" :aria-pressed="copy.weekdays.includes(i)" :class="['rounded-4 border px-2 py-1 text-xs', copy.weekdays.includes(i) ? 'border-outline-blue-2 bg-surface-blue-1' : 'border-outline-gray-2']" @click="toggleDay(copy.weekdays, i)">{{ d }}</button></div>
    </div>
    <p v-if="copy.result" class="rounded-5 bg-surface-green-1 p-3 text-sm text-ink-green-3">{{ copy.result }}</p>
  </Modal>
</template>
