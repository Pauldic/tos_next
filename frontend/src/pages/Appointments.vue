<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, PageHeader, PageHeaderTitle } from 'frappe-ui'
import Modal from '../components/Modal.vue'
import Field from '../components/Field.vue'
import ContainerPick from '../components/ContainerPick.vue'
import PartyPicker from '../components/PartyPicker.vue'
import { act, gateApi, tos } from '../api'
import { useTerminal } from '../composables/useTerminal'
import { usePolling } from '../composables/usePolling'

const { selected, current } = useTerminal()
const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
const date = ref(iso(new Date()))
const tab = ref<'slots' | 'overrides'>('slots')
const slots = ref<any[]>([])
const appts = ref<any[]>([])
const pending = ref<any[]>([])
const activeSlot = ref('')
const error = ref('')

async function refresh() {
  try {
    const [s, a, o] = await Promise.all([
      tos('capacity_for_day', { date: date.value, terminal: selected.value }),
      gateApi('appointments_for_day', { date: date.value, terminal: selected.value }),
      gateApi('pending_overrides', { terminal: selected.value }),
    ])
    slots.value = s as any[]
    appts.value = a as any[]
    pending.value = o as any[]
    if (!activeSlot.value || !slots.value.find((x) => x.name === activeSlot.value)) activeSlot.value = slots.value[0]?.name || ''
    error.value = ''
  } catch (e: any) { error.value = e.message }
}
usePolling(refresh, selected, 20000)
watch(date, () => { activeSlot.value = ''; refresh() })

function shift(days: number) {
  const d = new Date(date.value + 'T00:00:00')
  d.setDate(d.getDate() + days)
  date.value = iso(d)
}
const time = (t?: string) => (t || '').slice(0, 5)
const pct = (s: any) => (s.capacity ? Math.round((s.booked / s.capacity) * 100) : 0)
const barTone = (s: any) => (s.is_closed ? 'bg-surface-gray-4' : pct(s) >= 100 ? 'bg-surface-red-5' : pct(s) >= 80 ? 'bg-surface-amber-2' : 'bg-surface-blue-3')
const statusTheme = (s: string) => ({ Booked: 'blue', Arrived: 'green', 'In Progress': 'green', Completed: 'gray', Late: 'orange', 'No-show': 'red', Cancelled: 'gray' } as Record<string, string>)[s] || 'gray'
const slotAppts = computed(() => appts.value.filter((a) => a.slot === activeSlot.value))
const slotObj = computed(() => slots.value.find((s) => s.name === activeSlot.value))
const totals = computed(() => ({ booked: slots.value.reduce((n, s) => n + Number(s.booked || 0), 0), cap: slots.value.reduce((n, s) => n + Number(s.capacity || 0), 0) }))

// ---- book ----
const ALL_MOVES = ['Export Drop', 'Empty Return', 'Import Pickup', 'Empty Pickup']
const book = reactive({ open: false, slot: '', carrier: '', truck: '', driver: '', move_type: ALL_MOVES[0], container: '', booking_ref: '', override: '', error: '', loading: false })
const overrides = ref<any[]>([])
async function openBook() {
  Object.assign(book, { open: true, slot: activeSlot.value, carrier: '', truck: '', driver: '', move_type: ALL_MOVES[0], container: '', booking_ref: '', override: '', error: '', loading: false })
  overrides.value = (await gateApi('approved_overrides', { terminal: selected.value })) as any[]
}

async function submitBook() {
  book.loading = true; book.error = ''
  try {
    await act('book_appointment', { slot: book.slot, carrier: book.carrier, truck: book.truck, driver: book.driver, move_type: book.move_type, container: book.container, booking_ref: book.booking_ref, override: book.override })
    book.open = false
    await refresh()
  } catch (e: any) { book.error = e.message } finally { book.loading = false }
}

// ---- cancel ----
const cancel = reactive({ open: false, name: '', reason: '', error: '', loading: false })
async function submitCancel() {
  cancel.loading = true; cancel.error = ''
  try { await act('cancel_appointment', { name: cancel.name, reason: cancel.reason }); cancel.open = false; await refresh() }
  catch (e: any) { cancel.error = e.message } finally { cancel.loading = false }
}

// ---- request override ----
const OVERRIDE_TYPES = ['No Appointment', 'Over Capacity', 'Outside Slot Window', 'Details Changed']
const REASONS = ['Vessel Delay', 'Customs Request', 'Equipment Breakdown', 'Emergency', 'Regulator or Government', 'Customer Escalation', 'Other']
const req = reactive({ open: false, override_type: OVERRIDE_TYPES[0], reason_category: REASONS[0], reason: '', carrier: '', truck: '', driver: '', appointment: '', slot: '', error: '', loading: false })
function openReq() { Object.assign(req, { open: true, override_type: OVERRIDE_TYPES[0], reason_category: REASONS[0], reason: '', carrier: '', truck: '', driver: '', appointment: '', slot: activeSlot.value, error: '', loading: false }) }
async function submitReq() {
  req.loading = true; req.error = ''
  try {
    await act('request_override', { terminal: selected.value, override_type: req.override_type, reason_category: req.reason_category, reason: req.reason, carrier: req.carrier, truck: req.truck, driver: req.driver, appointment: req.appointment, slot: req.slot })
    req.open = false; tab.value = 'overrides'; await refresh()
  } catch (e: any) { req.error = e.message } finally { req.loading = false }
}

// ---- decide ----
const decide = reactive({ open: false, name: '', decision: 'approve', note: '', error: '', loading: false })
function openDecide(name: string, decision: string) { Object.assign(decide, { open: true, name, decision, note: '', error: '', loading: false }) }
async function submitDecide() {
  decide.loading = true; decide.error = ''
  try { await act('decide_override', { name: decide.name, decision: decide.decision, note: decide.note }); decide.open = false; await refresh() }
  catch (e: any) { decide.error = e.message } finally { decide.loading = false }
}
</script>

<template>
  <PageHeader>
    <PageHeaderTitle title="Appointments" />
    <div class="flex items-center gap-2">
      <Button icon="lucide-chevron-left" aria-label="Previous day" @click="shift(-1)" />
      <input v-model="date" type="date" class="tos-input !w-auto" aria-label="Date" />
      <Button icon="lucide-chevron-right" aria-label="Next day" @click="shift(1)" />
      <Button label="Today" @click="date = iso(new Date())" />
    </div>
  </PageHeader>

  <div class="mx-auto max-w-[1300px] space-y-5 px-4 pb-10 pt-6 sm:px-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="inline-flex rounded-5 border border-outline-gray-2 p-0.5" role="tablist">
        <button v-for="t in [{ k: 'slots', l: 'Slots' }, { k: 'overrides', l: 'Overrides' }]" :key="t.k" role="tab" :aria-selected="tab === t.k" :class="['rounded-4 px-3 py-1 text-sm', tab === t.k ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-6']" @click="tab = t.k as any">
          {{ t.l }}<span v-if="t.k === 'overrides' && pending.length" class="ml-1.5 rounded-full bg-surface-amber-2 px-1.5 text-xs">{{ pending.length }}</span>
        </button>
      </div>
      <p class="text-sm text-ink-gray-6">{{ current?.terminal_name }} · {{ totals.booked }} of {{ totals.cap }} places booked</p>
    </div>

    <ErrorMessage v-if="error" :message="error" />

    <div v-if="tab === 'slots'" class="grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
      <ul class="h-fit divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
        <li v-for="s in slots" :key="s.name">
          <button :class="['w-full px-4 py-2.5 text-left', s.name === activeSlot ? 'bg-surface-blue-1' : 'hover:bg-surface-gray-1']" :aria-pressed="s.name === activeSlot" @click="activeSlot = s.name">
            <div class="flex items-center justify-between">
              <span class="text-base-medium tabular-nums text-ink-gray-8">{{ time(s.start_time) }}–{{ time(s.end_time) }}</span>
              <span class="text-sm tabular-nums text-ink-gray-6">{{ s.booked }}/{{ s.capacity }}<Badge v-if="s.is_closed" class="ml-2" theme="gray" label="Closed" /></span>
            </div>
            <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-gray-3"><div :class="['h-full rounded-full', barTone(s)]" :style="{ width: Math.min(100, pct(s)) + '%' }" /></div>
          </button>
        </li>
        <li v-if="!slots.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">No slots on this day. Generate them from a Slot Template in Desk.</li>
      </ul>

      <section class="rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
        <header class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-3">
          <div>
            <h2 class="text-base-medium text-ink-gray-9">{{ slotObj ? time(slotObj.start_time) + '–' + time(slotObj.end_time) : 'No slot selected' }}</h2>
            <p v-if="slotObj" class="text-xs text-ink-gray-5">{{ slotObj.move_types }} · {{ slotObj.capacity - slotObj.booked }} places left</p>
          </div>
          <div class="flex gap-2">
            <Button label="Request override" icon-left="lucide-shield-alert" :disabled="!slotObj" @click="openReq" />
            <Button variant="solid" label="Book" icon-left="lucide-plus" :disabled="!slotObj || slotObj.is_closed" @click="openBook" />
          </div>
        </header>
        <ul class="divide-y divide-outline-gray-1">
          <li v-for="a in slotAppts" :key="a.name" class="flex items-center gap-3 px-4 py-2.5">
            <span :class="[a.direction === 'In' ? 'lucide-log-in' : 'lucide-log-out', 'size-4 shrink-0 text-ink-gray-5']" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-base-medium text-ink-gray-8">{{ a.truck }} <span class="text-ink-gray-5">· {{ a.move_type }}</span></p>
              <p class="truncate text-sm text-ink-gray-5">{{ a.name }} · {{ a.carrier }}<template v-if="a.container"> · {{ a.container }}</template><template v-if="a.override"> · override {{ a.override }}</template></p>
            </div>
            <Badge :theme="statusTheme(a.status)" :label="a.status" />
            <Button v-if="['Booked', 'Late'].includes(a.status)" variant="ghost" icon="lucide-x" aria-label="Cancel appointment" tooltip="Cancel" @click="Object.assign(cancel, { open: true, name: a.name, reason: '', error: '' })" />
          </li>
          <li v-if="!slotAppts.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">No appointments in this slot.</li>
        </ul>
      </section>
    </div>

    <section v-else class="rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
      <header class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-3">
        <h2 class="text-base-medium text-ink-gray-9">Waiting for a decision</h2>
        <Button label="Request override" icon-left="lucide-shield-alert" @click="openReq" />
      </header>
      <ul class="divide-y divide-outline-gray-1">
        <li v-for="o in pending" :key="o.name" class="px-4 py-3">
          <div class="flex flex-wrap items-center gap-2">
            <p class="text-base-medium text-ink-gray-8">{{ o.override_type }}</p>
            <Badge theme="orange" :label="o.reason_category" />
            <span class="text-sm text-ink-gray-5">{{ o.name }} · requested by {{ o.requested_by }}</span>
          </div>
          <p class="mt-1 text-sm text-ink-gray-7">{{ o.reason }}</p>
          <p class="mt-1 text-xs text-ink-gray-5">{{ [o.carrier, o.truck, o.appointment, o.slot].filter(Boolean).join(' · ') }}</p>
          <div class="mt-2 flex gap-2">
            <Button variant="solid" label="Approve" @click="openDecide(o.name, 'approve')" />
            <Button label="Reject" theme="red" @click="openDecide(o.name, 'reject')" />
          </div>
        </li>
        <li v-if="!pending.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">No overrides waiting.</li>
      </ul>
    </section>
  </div>

  <Modal :open="book.open" title="Book appointment" confirm-label="Book" :loading="book.loading" :error="book.error" wide @close="book.open = false" @confirm="submitBook">
    <Field label="Slot"><select v-model="book.slot" class="tos-input"><option v-for="s in slots" :key="s.name" :value="s.name">{{ time(s.start_time) }}–{{ time(s.end_time) }} ({{ s.capacity - s.booked }} left)</option></select></Field>
    <PartyPicker v-model:carrier="book.carrier" v-model:truck="book.truck" v-model:driver="book.driver" />
    <div class="grid grid-cols-2 gap-3">
      <Field label="Move"><select v-model="book.move_type" class="tos-input"><option v-for="m in ALL_MOVES" :key="m" :value="m">{{ m }}</option></select></Field>
      <Field label="Container"><ContainerPick v-model="book.container" /></Field>
      <Field label="Booking reference"><input v-model="book.booking_ref" class="tos-input" /></Field>
      <Field label="Approved override" hint="Only for a full slot or a closed window."><select v-model="book.override" class="tos-input"><option value="">None</option><option v-for="o in overrides" :key="o.name" :value="o.name">{{ o.name }} · {{ o.override_type }}</option></select></Field>
    </div>
  </Modal>

  <Modal :open="cancel.open" title="Cancel appointment" confirm-label="Cancel appointment" :loading="cancel.loading" :error="cancel.error" @close="cancel.open = false" @confirm="submitCancel">
    <Field :label="'Reason for cancelling ' + cancel.name"><textarea v-model="cancel.reason" rows="3" class="tos-input" /></Field>
  </Modal>

  <Modal :open="req.open" title="Request an override" confirm-label="Send for approval" :loading="req.loading" :error="req.error" wide @close="req.open = false" @confirm="submitReq">
    <div class="grid grid-cols-2 gap-3">
      <Field label="What needs overriding"><select v-model="req.override_type" class="tos-input"><option v-for="t in OVERRIDE_TYPES" :key="t" :value="t">{{ t }}</option></select></Field>
      <Field label="Category"><select v-model="req.reason_category" class="tos-input"><option v-for="r in REASONS" :key="r" :value="r">{{ r }}</option></select></Field>
    </div>
    <Field label="Reason" hint="At least 20 characters. This is part of the audit record."><textarea v-model="req.reason" rows="3" class="tos-input" /></Field>
    <PartyPicker v-model:carrier="req.carrier" v-model:truck="req.truck" v-model:driver="req.driver" />
    <div class="grid grid-cols-2 gap-3">
      <Field v-if="req.override_type === 'Over Capacity'" label="Slot"><select v-model="req.slot" class="tos-input"><option v-for="s in slots" :key="s.name" :value="s.name">{{ time(s.start_time) }}–{{ time(s.end_time) }}</option></select></Field>
      <Field v-if="['Outside Slot Window', 'Details Changed'].includes(req.override_type)" label="Appointment"><select v-model="req.appointment" class="tos-input"><option value="">Choose…</option><option v-for="a in appts" :key="a.name" :value="a.name">{{ a.name }} · {{ a.truck }} · {{ time(a.start_time) }}</option></select></Field>
    </div>
  </Modal>

  <Modal :open="decide.open" :title="(decide.decision === 'approve' ? 'Approve ' : 'Reject ') + decide.name" :confirm-label="decide.decision === 'approve' ? 'Approve' : 'Reject'" :loading="decide.loading" :error="decide.error" @close="decide.open = false" @confirm="submitDecide">
    <Field label="Decision note" hint="Required, and kept in the audit record. You cannot approve your own request."><textarea v-model="decide.note" rows="3" class="tos-input" /></Field>
  </Modal>
</template>
