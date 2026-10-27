<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button, ErrorMessage } from 'frappe-ui'
import Modal from './Modal.vue'

const props = defineProps<{ appt: any; ctx: any }>()
defineEmits<{ close: [] }>()

// What the gate scanner reads. Part 2 of the carrier flow reads this exact format.
const payload = computed(() => `TOSAPPT|${props.appt.name}|${props.appt.qr_token}`)
const img = ref('')
const error = ref('')

onMounted(async () => {
  try {
    const QR = await import('qrcode')
    img.value = await QR.toDataURL(payload.value, { width: 320, margin: 2, errorCorrectionLevel: 'M' })
  } catch (e: any) { error.value = 'Could not draw the QR code. The check-in code below still works.' }
})

const hm = (t?: string) => (t || '').slice(0, 5)
const shift = (t: string, mins: number) => {
  const [h, m] = (t || '00:00').split(':').map(Number)
  const x = (((h * 60 + m + mins) % 1440) + 1440) % 1440
  return String(Math.floor(x / 60)).padStart(2, '0') + ':' + String(x % 60).padStart(2, '0')
}
const date = computed(() => new Date(props.appt.slot_date + 'T00:00:00').toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }))
const window_ = computed(() => `${shift(hm(props.appt.start_time), -(props.ctx.early_minutes ?? 30))} to ${shift(hm(props.appt.end_time), props.ctx.late_minutes ?? 60)}`)
const driverName = computed(() => props.ctx.drivers?.find((d: any) => d.name === props.appt.driver)?.full_name || props.appt.driver)
const rows = computed(() => [
  ['Appointment', props.appt.name], ['Date', date.value], ['Slot', `${hm(props.appt.start_time)}–${hm(props.appt.end_time)}`],
  ['Arrive between', window_.value], ['Job', props.appt.move_type], ['Truck', props.appt.truck], ['Driver', driverName.value],
  ...(props.appt.container ? [['Container', props.appt.container]] : []), ...(props.appt.booking_ref ? [['Booking', props.appt.booking_ref]] : []),
])

function save() {
  const a = document.createElement('a')
  a.href = img.value
  a.download = `${props.appt.name}.png`
  a.click()
}
const esc = (s: string) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))
function print() {
  const w = window.open('', '_blank', 'width=480,height=720')
  if (!w) { error.value = 'Your browser blocked the print window. Allow pop-ups, or use Save image.'; return }
  w.document.write(`<!doctype html><title>${esc(props.appt.name)}</title><style>
    body{font:16px system-ui,sans-serif;margin:24px;color:#111}h1{font-size:20px;margin:0 0 4px}img{width:260px;height:260px;display:block;margin:12px 0}
    table{border-collapse:collapse}td{padding:3px 12px 3px 0;vertical-align:top}td:first-child{color:#555}.code{font:600 18px ui-monospace,monospace;letter-spacing:.08em}</style>
    <h1>${esc(props.ctx.terminal_name || 'Terminal')} gate pass</h1><img src="${img.value}" alt="QR code">
    <div class="code">${esc(props.appt.qr_token)}</div><table>${rows.value.map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join('')}</table>`)
  w.document.close()
  w.focus()
  setTimeout(() => w.print(), 300)
}
</script>

<template>
  <Modal :open="true" title="Gate pass" hide-confirm @close="$emit('close')">
    <div class="flex flex-col items-center">
      <img v-if="img" :src="img" alt="QR code for the gate" class="size-60 rounded-4 border border-outline-gray-1 bg-white p-1" />
      <div v-else class="flex size-60 items-center justify-center text-sm text-ink-gray-5">Drawing…</div>
      <p class="mt-3 font-mono text-lg font-semibold tracking-widest text-ink-gray-9">{{ appt.qr_token }}</p>
      <p class="text-xs text-ink-gray-5">If the scanner fails, read this code to the gate clerk.</p>
    </div>
    <dl class="divide-y divide-outline-gray-1 rounded-5 border border-outline-gray-1 text-sm">
      <div v-for="r in rows" :key="r[0]" class="flex justify-between gap-4 px-3 py-1.5"><dt class="text-ink-gray-5">{{ r[0] }}</dt><dd class="text-right text-ink-gray-9">{{ r[1] }}</dd></div>
    </dl>
    <ErrorMessage v-if="error" :message="error" />
    <div class="flex gap-2">
      <Button class="flex-1" icon-left="lucide-download" label="Save image" :disabled="!img" @click="save" />
      <Button class="flex-1" icon-left="lucide-printer" label="Print" :disabled="!img" @click="print" />
    </div>
  </Modal>
</template>
