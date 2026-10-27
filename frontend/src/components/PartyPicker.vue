<script setup lang="ts">
import { ref, watch } from 'vue'
import Field from './Field.vue'
import { gateApi } from '../api'

// Carrier, then that carrier's trucks and drivers.
const carrier = defineModel<string>('carrier', { default: '' })
const truck = defineModel<string>('truck', { default: '' })
const driver = defineModel<string>('driver', { default: '' })
const carriers = ref<any[]>([])
const trucks = ref<any[]>([])
const drivers = ref<any[]>([])

async function load(c: string) {
  const r = (await gateApi('lookups', { carrier: c })) as any
  carriers.value = r.carriers
  trucks.value = r.trucks
  drivers.value = r.drivers
}
load(carrier.value)
watch(carrier, (c, old) => {
  if (old !== undefined && c !== old) { truck.value = ''; driver.value = '' }
  load(c)
})
</script>

<template>
  <Field label="Carrier">
    <select v-model="carrier" class="tos-input"><option value="">Choose…</option><option v-for="c in carriers" :key="c.name" :value="c.name">{{ c.carrier_name || c.name }}</option></select>
  </Field>
  <div class="grid grid-cols-2 gap-3">
    <Field label="Truck">
      <select v-model="truck" class="tos-input" :disabled="!carrier"><option value="">Choose…</option><option v-for="t in trucks" :key="t.name" :value="t.name">{{ t.name }}</option></select>
    </Field>
    <Field label="Driver">
      <select v-model="driver" class="tos-input" :disabled="!carrier"><option value="">Choose…</option><option v-for="d in drivers" :key="d.name" :value="d.name">{{ d.driver_name || d.name }}</option></select>
    </Field>
  </div>
</template>
