<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, ErrorMessage, useColorScheme } from 'frappe-ui'
import Modal from '../components/Modal.vue'
import Field from '../components/Field.vue'
import { portalAct, portalApi } from '../api'
import { logout } from '../logout'

const router = useRouter()
const { resolvedColorScheme, toggleColorScheme } = useColorScheme()
const fleet = ref<any>(null)
const error = ref('')
const carrier = ref('')

async function load() {
  try { fleet.value = await portalApi('portal_fleet'); carrier.value ||= fleet.value.carriers[0]?.name || '' } catch (e: any) { error.value = e.message }
}
onMounted(load)

const trucks = computed(() => (fleet.value?.trucks || []).filter((t: any) => t.carrier === carrier.value))
const drivers = computed(() => (fleet.value?.drivers || []).filter((d: any) => d.carrier === carrier.value))

const TYPES = ['Tractor and Trailer', 'Rigid', 'Terminal Tractor']
const LENGTHS = ['20 ft only', 'Up to 40 ft', 'Up to 45 ft']
const t = reactive({ open: false, name: '', plate_no: '', truck_type: TYPES[0], max_container_length: LENGTHS[1], rfid_tag: '', error: '', loading: false })
const d = reactive({ open: false, name: '', full_name: '', phone: '', licence_no: '', licence_expiry: '', error: '', loading: false })

const addTruck = () => Object.assign(t, { open: true, name: '', plate_no: '', truck_type: TYPES[0], max_container_length: LENGTHS[1], rfid_tag: '', error: '' })
const editTruck = (x: any) => Object.assign(t, { open: true, name: x.name, plate_no: x.plate_no, truck_type: x.truck_type, max_container_length: x.max_container_length, rfid_tag: x.rfid_tag || '', error: '' })
const addDriver = () => Object.assign(d, { open: true, name: '', full_name: '', phone: '', licence_no: '', licence_expiry: '', error: '' })
const editDriver = (x: any) => Object.assign(d, { open: true, name: x.name, full_name: x.full_name, phone: x.phone || '', licence_no: x.licence_no, licence_expiry: x.licence_expiry, error: '' })

async function saveTruck() {
  t.loading = true; t.error = ''
  try { await portalAct('portal_save_truck', { carrier: carrier.value, name: t.name, plate_no: t.plate_no, truck_type: t.truck_type, max_container_length: t.max_container_length, rfid_tag: t.rfid_tag }); t.open = false; await load() }
  catch (e: any) { t.error = e.message } finally { t.loading = false }
}
async function saveDriver() {
  d.loading = true; d.error = ''
  try { await portalAct('portal_save_driver', { carrier: carrier.value, name: d.name, full_name: d.full_name, phone: d.phone, licence_no: d.licence_no, licence_expiry: d.licence_expiry }); d.open = false; await load() }
  catch (e: any) { d.error = e.message } finally { d.loading = false }
}
const prettyDate = (s: string) => new Date(s + 'T00:00:00').toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
</script>

<template>
  <div class="mx-auto flex min-h-screen max-w-2xl flex-col px-4 pb-12">
    <header class="sticky top-0 z-10 -mx-4 mb-5 flex items-center justify-between border-b border-outline-gray-1 bg-surface-base/95 px-4 py-3 backdrop-blur">
      <div class="flex items-center gap-2">
        <Button variant="ghost" icon="lucide-arrow-left" aria-label="Back to booking" @click="router.push('/portal')" />
        <h1 class="text-lg-semibold text-ink-gray-9">My fleet</h1>
      </div>
      <div class="flex items-center gap-2">
        <Button :icon="resolvedColorScheme === 'dark' ? 'lucide-sun' : 'lucide-moon'" aria-label="Switch light and dark mode" @click="toggleColorScheme" />
        <Button icon="lucide-log-out" label="Log out" @click="logout" />
      </div>
    </header>

    <ErrorMessage v-if="error" class="mb-4 whitespace-pre-line rounded-5 bg-surface-red-1 p-3" :message="error" />

    <template v-if="fleet">
      <Field v-if="fleet.carriers.length > 1" label="Carrier" class="mb-4"><select v-model="carrier" class="tos-input"><option v-for="c in fleet.carriers" :key="c.name" :value="c.name">{{ c.carrier_name || c.name }}</option></select></Field>

      <section class="mb-8">
        <div class="mb-2 flex items-center justify-between"><h2 class="text-base-medium text-ink-gray-9">Trucks <span class="text-ink-gray-5">· {{ trucks.length }}</span></h2><Button variant="solid" icon-left="lucide-plus" label="Add truck" @click="addTruck" /></div>
        <ul class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
          <li v-for="x in trucks" :key="x.name" class="flex items-center gap-3 px-4 py-3">
            <div class="min-w-0 flex-1"><p class="text-base-medium text-ink-gray-9">{{ x.plate_no }}</p><p class="truncate text-sm text-ink-gray-5">{{ x.truck_type }} · {{ x.max_container_length }}<template v-if="x.rfid_tag"> · RFID {{ x.rfid_tag }}</template></p>
              <p v-if="x.is_blocked" class="mt-1 text-sm text-ink-red-3">Blocked by the terminal: {{ x.block_reason }}</p></div>
            <Badge v-if="x.is_blocked" theme="red" label="Blocked" />
            <Button v-else variant="ghost" label="Edit" @click="editTruck(x)" />
          </li>
          <li v-if="!trucks.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">No trucks yet. Add the trucks you will send.</li>
        </ul>
      </section>

      <section>
        <div class="mb-2 flex items-center justify-between"><h2 class="text-base-medium text-ink-gray-9">Drivers <span class="text-ink-gray-5">· {{ drivers.length }}</span></h2><Button variant="solid" icon-left="lucide-plus" label="Add driver" @click="addDriver" /></div>
        <ul class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-1 bg-surface-white shadow-sm">
          <li v-for="x in drivers" :key="x.name" class="flex items-center gap-3 px-4 py-3">
            <div class="min-w-0 flex-1"><p class="text-base-medium text-ink-gray-9">{{ x.full_name }}</p><p class="truncate text-sm text-ink-gray-5">Licence {{ x.licence_no }} · expires {{ prettyDate(x.licence_expiry) }}<template v-if="x.phone"> · {{ x.phone }}</template></p>
              <p v-if="x.is_blocked" class="mt-1 text-sm text-ink-red-3">Blocked by the terminal: {{ x.block_reason }}</p></div>
            <Badge v-if="x.is_blocked" theme="red" label="Blocked" />
            <Badge v-else-if="x.licence_state === 'expired'" theme="red" label="Licence expired" />
            <Badge v-else-if="x.licence_state === 'soon'" theme="orange" label="Expires soon" />
            <Button v-if="!x.is_blocked" variant="ghost" label="Edit" @click="editDriver(x)" />
          </li>
          <li v-if="!drivers.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">No drivers yet.</li>
        </ul>
        <p class="mt-3 text-xs text-ink-gray-5">A driver with an expired licence cannot enter the terminal. Update the expiry date once the licence is renewed.</p>
      </section>
    </template>
    <p v-else-if="!error" class="py-20 text-center text-sm text-ink-gray-5">Loading…</p>
  </div>

  <Modal :open="t.open" :title="t.name ? 'Edit truck' : 'Add truck'" :loading="t.loading" :error="t.error" @close="t.open = false" @confirm="saveTruck">
    <Field label="Plate number" :hint="t.name ? 'The plate cannot be changed. Add a new truck instead.' : undefined"><input v-model="t.plate_no" class="tos-input uppercase" :disabled="!!t.name" autocomplete="off" /></Field>
    <div class="grid grid-cols-2 gap-3">
      <Field label="Type"><select v-model="t.truck_type" class="tos-input"><option v-for="x in TYPES" :key="x">{{ x }}</option></select></Field>
      <Field label="Largest container"><select v-model="t.max_container_length" class="tos-input"><option v-for="x in LENGTHS" :key="x">{{ x }}</option></select></Field>
    </div>
    <Field label="RFID tag (optional)"><input v-model="t.rfid_tag" class="tos-input" /></Field>
  </Modal>

  <Modal :open="d.open" :title="d.name ? 'Edit driver' : 'Add driver'" :loading="d.loading" :error="d.error" @close="d.open = false" @confirm="saveDriver">
    <Field label="Full name"><input v-model="d.full_name" class="tos-input" /></Field>
    <div class="grid grid-cols-2 gap-3">
      <Field label="Licence number"><input v-model="d.licence_no" class="tos-input uppercase" /></Field>
      <Field label="Licence expires"><input v-model="d.licence_expiry" type="date" class="tos-input" /></Field>
    </div>
    <Field label="Phone (optional)"><input v-model="d.phone" type="tel" class="tos-input" /></Field>
  </Modal>
</template>
