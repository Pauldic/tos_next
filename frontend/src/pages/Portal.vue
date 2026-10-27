<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Badge, Button, ErrorMessage, useColorScheme } from 'frappe-ui'
import Modal from '../components/Modal.vue'
import Field from '../components/Field.vue'
import AppointmentPass from '../components/AppointmentPass.vue'
import { portalAct, portalApi } from '../api'
import { useRouter } from 'vue-router'

const router = useRouter()

const { resolvedColorScheme, toggleColorScheme } = useColorScheme()

const ctx = ref<any>(null)
const appts = ref<any[]>([])
const slots = ref<any[]>([])
const error = ref('')
const loadingSlots = ref(false)

const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d })

const MOVES = [
  { v: 'Export Drop', label: 'Drop off an export', sub: 'Gate In, loaded' },
  { v: 'Empty Return', label: 'Return an empty', sub: 'Gate In, empty' },
  { v: 'Import Pickup', label: 'Pick up an import', sub: 'Gate Out, loaded' },
  { v: 'Empty Pickup', label: 'Pick up an empty', sub: 'Gate Out, empty' },
]
const form = reactive({ move: 'Export Drop', date: iso(new Date()), slot: '', carrier: '', truck: '', driver: '', container: '', booking_ref: '' })
const booking = ref(false)
const done = ref<any>(null)
const pass = ref<any>(null)
const openPass = (name: string) => (pass.value = appts.value.find((a) => a.name === name) || null)

async function loadCtx() {
  try {
    ctx.value = await portalApi('portal_context')
    form.carrier = ctx.value.carriers[0]?.name || ''
  } catch (e: any) { error.value = e.message }
}
async function loadAppts() {
  try { appts.value = (await portalApi('portal_appointments')) as any[] } catch (e: any) { error.value = e.message }
}
async function loadSlots() {
  form.slot = ''
  loadingSlots.value = true
  try { slots.value = (await portalApi('portal_slots', { date: form.date, move_type: form.move })) as any[] } catch (e: any) { error.value = e.message } finally { loadingSlots.value = false }
}
onMounted(async () => { await loadCtx(); if (ctx.value) { loadAppts(); loadSlots() } })

const trucks = computed(() => (ctx.value?.trucks || []).filter((t: any) => t.carrier === form.carrier))
const drivers = computed(() => (ctx.value?.drivers || []).filter((d: any) => d.carrier === form.carrier))
const isPickup = computed(() => form.move.endsWith('Pickup'))
const needsRef = computed(() => form.move === 'Export Drop')
const chosen = computed(() => slots.value.find((s) => s.name === form.slot))
const ready = computed(() => form.slot && form.truck && form.driver && (!needsRef.value || form.booking_ref))

function pickMove(v: string) { form.move = v; loadSlots() }
function pickDay(d: Date) { form.date = iso(d); loadSlots() }

async function book() {
  booking.value = true
  error.value = ''
  try {
    done.value = await portalAct('portal_book', { slot: form.slot, carrier: form.carrier, truck: form.truck, driver: form.driver, move_type: form.move, container: form.container, booking_ref: form.booking_ref })
    Object.assign(form, { slot: '', container: '', booking_ref: '' })
    await Promise.all([loadAppts(), loadSlots()])
  } catch (e: any) { error.value = e.message } finally { booking.value = false }
}

const cancel = reactive({ open: false, name: '', reason: '', error: '', loading: false })
async function submitCancel() {
  cancel.loading = true; cancel.error = ''
  try { await portalAct('portal_cancel', { name: cancel.name, reason: cancel.reason }); cancel.open = false; await Promise.all([loadAppts(), loadSlots()]) }
  catch (e: any) { cancel.error = e.message } finally { cancel.loading = false }
}

const theme = (s: string) => ({ Booked: 'blue', Arrived: 'green', 'In Progress': 'green', Completed: 'gray', Late: 'orange', 'No-show': 'red', Cancelled: 'gray' } as Record<string, string>)[s] || 'gray'
const hm = (t?: string) => (t || '').slice(0, 5)
const dayLabel = (d: Date, i: number) => (i === 0 ? 'Today' : i === 1 ? 'Tomorrow' : d.toLocaleDateString([], { weekday: 'short', day: 'numeric' }))
const prettyDate = (s: string) => new Date(s + 'T00:00:00').toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })
const upcoming = computed(() => appts.value.filter((a) => !['Cancelled', 'Completed', 'No-show'].includes(a.status)))
const past = computed(() => appts.value.filter((a) => ['Cancelled', 'Completed', 'No-show'].includes(a.status)))
</script>

<template>
  <div class="mx-auto flex min-h-screen max-w-2xl flex-col px-4 pb-12">
    <header class="sticky top-0 z-10 -mx-4 mb-5 flex items-center justify-between border-b border-outline-gray-1 bg-surface-base/95 px-4 py-3 backdrop-blur">
      <div class="min-w-0">
        <h1 class="text-lg-semibold text-ink-gray-9">Book a terminal slot</h1>
        <p class="truncate text-sm text-ink-gray-5">{{ ctx?.terminal_name || 'Carrier portal' }}</p>
      </div>
      <div class="flex items-center gap-2">
        <Button icon-left="lucide-truck" label="My fleet" @click="router.push('/portal/fleet')" />
        <Button :icon="resolvedColorScheme === 'dark' ? 'lucide-sun' : 'lucide-moon'" aria-label="Switch light and dark mode" @click="toggleColorScheme" />
      </div>
    </header>

    <ErrorMessage v-if="error" class="mb-4 whitespace-pre-line rounded-5 bg-surface-red-1 p-3" :message="error" />

    <template v-if="ctx">
      <div v-for="c in ctx.carriers.filter((x: any) => x.is_blocked)" :key="c.name" class="mb-4 rounded-5 bg-surface-red-1 p-3 text-sm text-ink-red-3">{{ c.carrier_name || c.name }} is blocked: {{ c.block_reason }}</div>

      <section v-if="done" class="mb-5 rounded-6 border border-outline-green-2 bg-surface-green-1 p-4">
        <p class="text-base-medium text-ink-green-3">Booked: {{ done.name }}</p>
        <p class="mt-1 text-sm text-ink-green-3">Your gate pass is ready. The driver shows it at the gate.</p>
        <div class="mt-3 flex gap-2"><Button variant="solid" icon-left="lucide-qr-code" label="Show pass" @click="openPass(done.name)" /><Button variant="ghost" label="Dismiss" @click="done = null" /></div>
      </section>

      <section class="mb-8 space-y-5 rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
        <div>
          <p class="mb-2 text-sm text-ink-gray-6">1. What are you doing?</p>
          <div class="grid grid-cols-2 gap-2">
            <button v-for="m in MOVES" :key="m.v" :aria-pressed="form.move === m.v" :class="['min-h-[56px] rounded-5 border px-3 py-2 text-left', form.move === m.v ? 'border-outline-blue-2 bg-surface-blue-1' : 'border-outline-gray-2']" @click="pickMove(m.v)">
              <span class="block text-sm font-medium text-ink-gray-9">{{ m.label }}</span><span class="block text-xs text-ink-gray-5">{{ m.sub }}</span>
            </button>
          </div>
        </div>

        <div>
          <p class="mb-2 text-sm text-ink-gray-6">2. Which day and time?</p>
          <div class="-mx-1 mb-3 flex gap-2 overflow-x-auto px-1 pb-1">
            <button v-for="(d, i) in days" :key="i" :aria-pressed="form.date === iso(d)" :class="['min-h-[44px] shrink-0 rounded-5 border px-3 text-sm', form.date === iso(d) ? 'border-outline-blue-2 bg-surface-blue-1 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-7']" @click="pickDay(d)">{{ dayLabel(d, i) }}</button>
          </div>
          <div v-if="slots.length" class="grid grid-cols-3 gap-2 sm:grid-cols-4">
            <button v-for="s in slots" :key="s.name" :disabled="!s.left" :aria-pressed="form.slot === s.name" :class="['min-h-[52px] rounded-5 border px-2 py-1 text-center disabled:opacity-40', form.slot === s.name ? 'border-outline-blue-2 bg-surface-blue-1' : 'border-outline-gray-2']" @click="form.slot = s.name">
              <span class="block text-sm font-medium tabular-nums text-ink-gray-9">{{ s.start }}</span>
              <span class="block text-xs text-ink-gray-5">{{ s.left ? s.left + ' left' : 'Full' }}</span>
            </button>
          </div>
          <p v-else class="text-sm text-ink-gray-5">{{ loadingSlots ? 'Loading…' : 'No open slots for this day.' }}</p>
        </div>

        <div class="space-y-3">
          <p class="text-sm text-ink-gray-6">3. Who is coming?</p>
          <Field v-if="ctx.carriers.length > 1" label="Carrier">
            <select v-model="form.carrier" class="tos-input" @change="form.truck = ''; form.driver = ''"><option v-for="c in ctx.carriers" :key="c.name" :value="c.name">{{ c.carrier_name || c.name }}</option></select>
          </Field>
          <div class="grid grid-cols-2 gap-3">
            <Field label="Truck"><select v-model="form.truck" class="tos-input"><option value="">Choose…</option><option v-for="t in trucks" :key="t.name" :value="t.name">{{ t.name }}</option></select></Field>
            <Field label="Driver"><select v-model="form.driver" class="tos-input"><option value="">Choose…</option><option v-for="d in drivers" :key="d.name" :value="d.name">{{ d.full_name || d.name }}</option></select></Field>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <Field :label="isPickup ? 'Container number' : 'Container number (optional)'"><input v-model="form.container" class="tos-input" placeholder="MSCU1234567" autocomplete="off" /></Field>
            <Field :label="needsRef ? 'Booking reference' : 'Booking reference (optional)'"><input v-model="form.booking_ref" class="tos-input" /></Field>
          </div>
          <p v-if="!trucks.length || !drivers.length" class="text-sm text-ink-amber-3">There is no active {{ !trucks.length ? 'truck' : 'driver' }} on your account. Ask the terminal to add one.</p>
        </div>

        <Button class="!h-12 w-full" variant="solid" :disabled="!ready" :loading="booking" :label="chosen ? `Book ${prettyDate(form.date)} at ${chosen.start}` : 'Choose a time to book'" @click="book" />
      </section>

      <section class="mb-6">
        <h2 class="mb-2 text-base-medium text-ink-gray-9">Your appointments</h2>
        <ul class="space-y-3">
          <li v-for="a in upcoming" :key="a.name" class="rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="text-base-medium text-ink-gray-9">{{ prettyDate(a.slot_date) }} · {{ hm(a.start_time) }}–{{ hm(a.end_time) }}</p>
                <p class="text-sm text-ink-gray-5">{{ a.move_type }} · {{ a.truck }}<template v-if="a.container"> · {{ a.container }}</template></p>
              </div>
              <Badge :theme="theme(a.status)" :label="a.status" />
            </div>
            <div class="mt-2 flex items-center justify-between text-sm">
              <span class="text-ink-gray-5">{{ a.name }}</span>
              <span class="flex gap-1">
                <Button v-if="['Booked', 'Late', 'Arrived'].includes(a.status)" variant="subtle" icon-left="lucide-qr-code" label="Pass" @click="openPass(a.name)" />
                <Button v-if="['Booked', 'Late'].includes(a.status)" variant="ghost" label="Cancel" @click="Object.assign(cancel, { open: true, name: a.name, reason: '', error: '' })" />
              </span>
            </div>
          </li>
          <li v-if="!upcoming.length" class="rounded-6 border border-dashed border-outline-gray-2 p-6 text-center text-sm text-ink-gray-5">No upcoming appointments.</li>
        </ul>
        <details v-if="past.length" class="mt-4 text-sm text-ink-gray-6"><summary class="cursor-pointer">Recent history ({{ past.length }})</summary>
          <ul class="mt-2 divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-1 bg-surface-white">
            <li v-for="a in past" :key="a.name" class="flex items-center justify-between px-3 py-2"><span>{{ prettyDate(a.slot_date) }} · {{ a.truck }}</span><Badge :theme="theme(a.status)" :label="a.status" /></li>
          </ul>
        </details>
      </section>
    </template>
    <p v-else-if="!error" class="py-20 text-center text-sm text-ink-gray-5">Loading…</p>
  </div>

  <AppointmentPass v-if="pass" :appt="pass" :ctx="ctx" @close="pass = null" />

  <Modal :open="cancel.open" title="Cancel appointment" confirm-label="Cancel appointment" :loading="cancel.loading" :error="cancel.error" @close="cancel.open = false" @confirm="submitCancel">
    <Field :label="'Why are you cancelling ' + cancel.name + '?'"><textarea v-model="cancel.reason" rows="3" class="tos-input" /></Field>
  </Modal>
</template>
