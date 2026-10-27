<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Badge, Button, ErrorMessage, PageHeader, PageHeaderTitle } from 'frappe-ui'
import Modal from '../components/Modal.vue'
import Field from '../components/Field.vue'
import ContainerPick from '../components/ContainerPick.vue'
import PartyPicker from '../components/PartyPicker.vue'
import { act, gateApi, tos } from '../api'
import { useTerminal } from '../composables/useTerminal'
import { usePolling } from '../composables/usePolling'

const { selected, current } = useTerminal()
const lanes = ref<any[]>([])
const queue = ref<any[]>([])
const overrides = ref<any[]>([])
const error = ref('')

async function refresh() {
  try {
    const [g, o] = await Promise.all([tos('gate_board', { terminal: selected.value }), gateApi('approved_overrides', { terminal: selected.value })])
    lanes.value = (g as any).lanes
    queue.value = (g as any).arrival_queue
    overrides.value = o as any[]
    error.value = ''
  } catch (e: any) { error.value = e.message }
}
usePolling(refresh, selected, 5000)

const inLanes = computed(() => lanes.value.filter((l) => l.direction === 'In'))
const outLanes = computed(() => lanes.value.filter((l) => l.direction === 'Out'))

const laneTheme = (s: string) => ({ Open: 'green', Busy: 'blue', Closed: 'gray', Fault: 'red' } as Record<string, string>)[s] || 'gray'
const txTheme = (s: string) => ({ Processing: 'blue', 'On Hold': 'orange', Cleared: 'green', Completed: 'gray', Rejected: 'red' } as Record<string, string>)[s] || 'gray'
const dot = (r: string) => ({ Passed: 'bg-surface-green-3', Failed: 'bg-surface-red-5', Waived: 'bg-surface-amber-2', Pending: 'bg-surface-gray-4' } as Record<string, string>)[r] || 'bg-surface-gray-4'

// ---- doing something to a transaction ----
const busy = ref('')
const actError = ref('')
async function run(tx: any, action: string, args: Record<string, unknown> = {}) {
  busy.value = tx.name + action
  actError.value = ''
  try {
    await act('gate_action', { transaction: tx.name, action, ...args })
    await refresh()
    return true
  } catch (e: any) {
    actError.value = e.message
    return false
  } finally { busy.value = '' }
}

// a small prompt used by hold, fail, waive, turn away, release and OCR
const prompt = reactive({ open: false, tx: null as any, action: '', title: '', label: '', field: '', second: false, value: '', value2: '', error: '' })
function ask(tx: any, action: string, title: string, label: string, field: string) {
  Object.assign(prompt, { open: true, tx, action, title, label, field, second: false, value: '', value2: '', error: '' })
}
function askOcr(tx: any) {
  Object.assign(prompt, { open: true, tx, action: 'record_ocr', title: 'Record portal read', label: 'Container number', field: 'container_no', second: true, value: '', value2: '', error: '' })
}
async function submitPrompt() {
  const args: Record<string, unknown> = { [prompt.field]: prompt.value }
  if (prompt.second) args.confidence = prompt.value2
  const ok = await run(prompt.tx, prompt.action, args)
  if (ok) prompt.open = false
  else prompt.error = actError.value
}

// ---- start a visit ----
const visit = reactive({ open: false, lane: null as any, appointment: '', carrier: '', truck: '', driver: '', move_type: '', container: '', booking_ref: '', seal_no: '', override: '', error: '', loading: false })
const moves = (dir: string) => (dir === 'In' ? ['Export Drop', 'Empty Return'] : ['Import Pickup', 'Empty Pickup'])
function startVisit(lane: any) {
  Object.assign(visit, { open: true, lane, appointment: '', carrier: '', truck: '', driver: '', move_type: moves(lane.direction)[0], container: '', booking_ref: '', seal_no: '', override: '', error: '', loading: false })
}
const queueFor = computed(() => queue.value.filter((a) => visit.lane && moves(visit.lane.direction).includes(a.move_type)))
function pickAppointment() {
  const a = queue.value.find((x) => x.name === visit.appointment)
  if (!a) return
  Object.assign(visit, { carrier: a.carrier, move_type: a.move_type, container: a.container || '', booking_ref: a.booking_ref || '' })
  // truck and driver fill in after the carrier's lists load
  setTimeout(() => Object.assign(visit, { truck: a.truck, driver: a.driver || visit.driver }), 400)
}
async function submitVisit() {
  visit.loading = true
  visit.error = ''
  try {
    await act('start_visit', {
      lane: visit.lane.name, carrier: visit.carrier, truck: visit.truck, driver: visit.driver, move_type: visit.move_type,
      appointment: visit.appointment, override: visit.override, container: visit.container, booking_ref: visit.booking_ref, seal_no: visit.seal_no,
    })
    visit.open = false
    await refresh()
  } catch (e: any) { visit.error = e.message } finally { visit.loading = false }
}
const time = (t?: string) => (t || '').slice(0, 5)
</script>

<template>
  <PageHeader>
    <PageHeaderTitle title="Gate" />
    <span class="text-sm text-ink-gray-5">{{ current?.terminal_name }} · refreshes every 5 seconds</span>
  </PageHeader>

  <div class="mx-auto max-w-[1300px] space-y-6 px-4 pb-10 pt-6 sm:px-6">
    <ErrorMessage v-if="error" :message="error" />
    <ErrorMessage v-if="actError && !prompt.open" class="whitespace-pre-line" :message="actError" />

    <div class="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_300px]">
      <div class="space-y-6">
        <section v-for="grp in [{ title: 'Gate In', icon: 'lucide-log-in', list: inLanes }, { title: 'Gate Out', icon: 'lucide-log-out', list: outLanes }]" :key="grp.title">
          <h2 class="mb-3 flex items-center gap-2 text-base-medium text-ink-gray-9"><span :class="[grp.icon, 'size-4 text-ink-gray-5']" aria-hidden="true" />{{ grp.title }}</h2>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <article v-for="l in grp.list" :key="l.name" class="rounded-6 border border-outline-gray-1 bg-surface-white p-4 shadow-sm">
              <header class="flex items-center justify-between">
                <h3 class="text-base-medium text-ink-gray-9">Lane {{ l.lane_code }}</h3>
                <Badge :theme="laneTheme(l.status)" :label="l.status" />
              </header>

              <template v-if="l.transaction">
                <div class="mt-3 flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="truncate text-base-medium text-ink-gray-8">{{ l.transaction.truck }} <span class="text-ink-gray-5">· {{ l.transaction.move_type }}</span></p>
                    <p class="truncate text-sm text-ink-gray-5">{{ l.transaction.carrier }}<template v-if="l.transaction.container"> · {{ l.transaction.container }}</template></p>
                  </div>
                  <Badge :theme="txTheme(l.transaction.status)" :label="l.transaction.status" />
                </div>
                <p v-if="l.transaction.hold_reason" class="mt-2 rounded-4 bg-surface-amber-1 px-2 py-1 text-sm text-ink-amber-3">{{ l.transaction.hold_reason }}</p>
                <p v-if="l.transaction.override" class="mt-2 flex items-center gap-1 text-xs text-ink-amber-3"><span class="lucide-shield-check size-3.5" aria-hidden="true" />Entered on override {{ l.transaction.override }}</p>

                <ol class="mt-3 space-y-1.5">
                  <li v-for="(c, i) in l.transaction.checks" :key="c.step" class="flex items-center gap-2 text-sm" :aria-current="i === l.transaction.current_step && l.transaction.status === 'Processing' ? 'step' : undefined">
                    <span :class="['size-2.5 shrink-0 rounded-full', dot(c.result), i === l.transaction.current_step && c.result === 'Pending' && l.transaction.status === 'Processing' ? 'ring-2 ring-outline-blue-2' : '']" />
                    <span :class="i === l.transaction.current_step && c.result === 'Pending' ? 'text-ink-gray-9' : 'text-ink-gray-6'">{{ c.step }}</span>
                    <span class="text-xs text-ink-gray-5">{{ c.result !== 'Pending' ? c.result : '' }}</span>
                  </li>
                </ol>

                <div class="mt-4 flex flex-wrap gap-2">
                  <Button v-if="l.transaction.status === 'Processing'" variant="solid" label="Advance" :loading="busy === l.transaction.name + 'advance'" @click="run(l.transaction, 'advance')" />
                  <Button v-if="l.transaction.status === 'Cleared'" variant="solid" label="Let truck through" :loading="busy === l.transaction.name + 'complete'" @click="run(l.transaction, 'complete')" />
                  <Button v-if="l.transaction.status === 'On Hold'" variant="solid" label="Release hold" @click="ask(l.transaction, 'release_hold', 'Release the hold', 'Release note', 'note')" />
                  <Button v-if="['Processing', 'On Hold'].includes(l.transaction.status)" label="Portal read" @click="askOcr(l.transaction)" />
                  <Button v-if="l.transaction.status === 'Processing'" label="Hold" @click="ask(l.transaction, 'hold', 'Hold the truck', 'Reason', 'reason')" />
                  <Button v-if="l.transaction.status === 'Processing'" label="Fail step" theme="red" @click="ask(l.transaction, 'fail_step', 'Fail this step', 'What failed?', 'remarks')" />
                  <Button v-if="['Processing', 'On Hold'].includes(l.transaction.status)" label="Waive" @click="ask(l.transaction, 'waive_step', 'Waive this step', 'Why is it safe to waive?', 'note')" />
                  <Button v-if="['Processing', 'On Hold'].includes(l.transaction.status)" label="Turn away" theme="red" @click="ask(l.transaction, 'reject', 'Turn the truck away', 'Reason', 'reason')" />
                </div>
              </template>

              <div v-else class="mt-4">
                <p class="mb-3 text-sm text-ink-gray-5">{{ l.status === 'Open' ? 'Waiting for a truck.' : 'Not taking trucks.' }}</p>
                <Button v-if="l.status === 'Open'" icon-left="lucide-plus" label="Start visit" @click="startVisit(l)" />
              </div>
            </article>
            <p v-if="!grp.list.length" class="text-sm text-ink-gray-5">No lanes.</p>
          </div>
        </section>
      </div>

      <aside class="h-fit rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
        <header class="border-b border-outline-gray-1 px-4 py-3"><h2 class="text-base-medium text-ink-gray-9">Arriving soon</h2><p class="text-xs text-ink-gray-5">Slot starts within 90 minutes</p></header>
        <ul class="divide-y divide-outline-gray-1">
          <li v-for="a in queue" :key="a.name" class="px-4 py-2.5">
            <p class="text-base-medium text-ink-gray-8">{{ a.truck }} <span class="text-ink-gray-5">· {{ a.move_type }}</span></p>
            <p class="text-sm text-ink-gray-5">{{ time(a.start_time) }} · {{ a.minutes_to_slot >= 0 ? 'in ' + a.minutes_to_slot + ' min' : -a.minutes_to_slot + ' min ago' }}<Badge v-if="a.status === 'Late'" class="ml-2" theme="orange" label="Late" /></p>
          </li>
          <li v-if="!queue.length" class="px-4 py-6 text-center text-sm text-ink-gray-5">Nobody expected.</li>
        </ul>
      </aside>
    </div>
  </div>

  <Modal :open="prompt.open" :title="prompt.title" :error="prompt.error" confirm-label="Confirm" :loading="!!busy" @close="prompt.open = false" @confirm="submitPrompt">
    <Field :label="prompt.label"><textarea v-if="!prompt.second" v-model="prompt.value" rows="3" class="tos-input" /><input v-else v-model="prompt.value" class="tos-input" /></Field>
    <Field v-if="prompt.second" label="Confidence (%)"><input v-model="prompt.value2" type="number" min="0" max="100" class="tos-input" /></Field>
  </Modal>

  <Modal :open="visit.open" :title="'Start visit · Lane ' + (visit.lane?.lane_code || '')" confirm-label="Start visit" :loading="visit.loading" :error="visit.error" wide @close="visit.open = false" @confirm="submitVisit">
    <Field label="Appointment" :hint="current?.require_appointment ? 'This terminal requires an appointment. Without one, choose an approved override below.' : undefined">
      <select v-model="visit.appointment" class="tos-input" @change="pickAppointment">
        <option value="">No appointment (walk-in)</option>
        <option v-for="a in queueFor" :key="a.name" :value="a.name">{{ a.name }} · {{ a.truck }} · {{ time(a.start_time) }}</option>
      </select>
    </Field>
    <PartyPicker v-model:carrier="visit.carrier" v-model:truck="visit.truck" v-model:driver="visit.driver" />
    <div class="grid grid-cols-2 gap-3">
      <Field label="Move"><select v-model="visit.move_type" class="tos-input"><option v-for="m in moves(visit.lane?.direction || 'In')" :key="m" :value="m">{{ m }}</option></select></Field>
      <Field label="Container"><ContainerPick v-model="visit.container" /></Field>
      <Field label="Booking reference"><input v-model="visit.booking_ref" class="tos-input" /></Field>
      <Field label="Seal number"><input v-model="visit.seal_no" class="tos-input" /></Field>
    </div>
    <Field label="Approved override" hint="Only needed when the visit is outside the rules. The system tells you if one is required.">
      <select v-model="visit.override" class="tos-input">
        <option value="">None</option>
        <option v-for="o in overrides" :key="o.name" :value="o.name">{{ o.name }} · {{ o.override_type }} · {{ o.truck || o.carrier || o.appointment }}</option>
      </select>
    </Field>
  </Modal>
</template>
