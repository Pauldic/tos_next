<script setup lang="ts">
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import ContainerPick from './ContainerPick.vue'
import { blankJob as blank, dirOf, firstOf, type Job, type TxType } from '../jobs'

// The jobs of one truck visit: any mix of drop offs and pick ups. Shows at once whether they fit the truck's chassis;
// the server checks the same rule again when the appointment is saved.
const jobs = defineModel<Job[]>({ required: true })
const props = defineProps<{ types: TxType[]; chassis?: { name: string; max_container_length_ft: number; max_containers: number; max_total_length_ft: number } | null; lengths: number[]; staff?: boolean }>()

const isDrop = (m: string) => dirOf(props.types, m) === 'In'
const tx = (m: string) => props.types.find((t) => t.name === m)
const add = (dir?: 'In' | 'Out') => jobs.value.push(blank(firstOf(props.types, dir || 'In')))
const remove = (i: number) => jobs.value.splice(i, 1)
function preset(kind: 'in' | 'out' | 'both') {
  const i = blank(firstOf(props.types, 'In')), o = blank(firstOf(props.types, 'Out'))
  jobs.value = kind === 'in' ? [i] : kind === 'out' ? [o] : [i, o]
}
const visit = computed(() => {
  const d = jobs.value.some((j) => isDrop(j.move_type)), p = jobs.value.some((j) => !isDrop(j.move_type))
  return d && p ? 'Receive and deliver' : p ? 'Deliver (Gate Out)' : 'Receive (Gate In)'
})

function fits(ls: number[]) {
  const c = props.chassis
  if (!c || !ls.length) return ''
  if (ls.some((x) => x > c.max_container_length_ft)) return `A ${ls.find((x) => x > c.max_container_length_ft)} ft container does not fit a ${c.name} chassis (longest ${c.max_container_length_ft} ft).`
  if (ls.length > c.max_containers) return `A ${c.name} chassis carries at most ${c.max_containers} container${c.max_containers > 1 ? 's' : ''} at once.`
  if (ls.reduce((a, b) => a + b, 0) > c.max_total_length_ft) return `${ls.reduce((a, b) => a + b, 0)} ft of containers is more than the ${c.max_total_length_ft} ft this chassis carries.`
  return ''
}
const sizes = (drop: boolean) => jobs.value.filter((j) => isDrop(j.move_type) === drop && j.container_length).map((j) => Number(j.container_length))
const problems = computed(() => [fits(sizes(true)) && 'Receive: ' + fits(sizes(true)), fits(sizes(false)) && 'Deliver: ' + fits(sizes(false))].filter(Boolean) as string[])
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-sm text-ink-gray-6">Visit:</span>
      <Button size="sm" label="Receive" @click="preset('in')" />
      <Button size="sm" label="Deliver" @click="preset('out')" />
      <Button size="sm" label="Receive and deliver" @click="preset('both')" />
      <span class="ml-auto text-sm font-medium text-ink-gray-8">{{ visit }}</span>
    </div>
    <p v-if="chassis" class="text-xs text-ink-gray-5">Chassis: {{ chassis.name }}. At most {{ chassis.max_containers }} container{{ chassis.max_containers > 1 ? 's' : '' }}, longest {{ chassis.max_container_length_ft }} ft, {{ chassis.max_total_length_ft }} ft in total. What is received and what is delivered are each checked against it.</p>
    <ul class="space-y-2">
      <li v-for="(j, i) in jobs" :key="i" class="rounded-5 border border-outline-gray-2 p-3">
        <div class="flex items-center gap-2">
          <select v-model="j.move_type" class="tos-input" :aria-label="'Job ' + (i + 1)"><option v-for="m in types" :key="m.name" :value="m.name">{{ m.name }} · Gate {{ m.direction }}</option></select>
          <Button v-if="jobs.length > 1" variant="ghost" icon="lucide-x" aria-label="Remove this job" @click="remove(i)" />
        </div>
        <div class="mt-2 grid grid-cols-3 gap-2">
          <label class="block text-xs text-ink-gray-5">Size
            <select v-model="j.container_length" class="tos-input mt-1"><option value="">{{ j.container ? 'From container' : 'Choose…' }}</option><option v-for="l in lengths" :key="l" :value="l">{{ l }} ft</option></select>
          </label>
          <label class="block text-xs text-ink-gray-5">{{ tx(j.move_type)?.requires_container ? 'Container' : 'Container (optional)' }}
            <template v-if="staff"><ContainerPick v-model="j.container" /></template>
            <input v-else v-model="j.container" class="tos-input mt-1" placeholder="MSCU1234567" autocomplete="off" />
          </label>
          <label class="block text-xs text-ink-gray-5">{{ tx(j.move_type)?.requires_booking ? 'Booking reference' : 'Booking (optional)' }}
            <input v-model="j.booking_ref" class="tos-input mt-1" />
          </label>
        </div>
      </li>
    </ul>
    <Button icon-left="lucide-plus" label="Add another container" @click="add(isDrop(jobs[jobs.length - 1]?.move_type) ? 'Out' : 'In')" />
    <ul v-if="problems.length" class="space-y-1 rounded-5 bg-surface-red-1 p-3 text-sm text-ink-red-3"><li v-for="p in problems" :key="p">{{ p }}</li></ul>
  </div>
</template>
