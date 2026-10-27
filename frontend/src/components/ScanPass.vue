<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage } from 'frappe-ui'
import Modal from './Modal.vue'
import Field from './Field.vue'
import { act, gateApi } from '../api'

const props = defineProps<{ open: boolean; terminal: string; lanes: any[]; overrides: any[] }>()
const emit = defineEmits<{ close: []; started: [] }>()

const code = ref('')
const result = ref<any>(null)
const error = ref('')
const loading = ref(false)
const starting = ref(false)
const lane = ref('')
const override = ref('')
const input = ref<HTMLInputElement>()

const video = ref<HTMLVideoElement>()
const camOn = ref(false)
const camError = ref('')
let stream: MediaStream | null = null
let timer = 0

function reset() {
  code.value = ''; result.value = null; error.value = ''; lane.value = ''; override.value = ''; stopCam(); camError.value = ''
}
watch(() => props.open, async (o) => { if (o) { reset(); await nextTick(); input.value?.focus() } else stopCam() })
onBeforeUnmount(stopCam)

async function lookup(text = code.value) {
  if (!text.trim()) return
  loading.value = true; error.value = ''; result.value = null
  try {
    result.value = await gateApi('scan_pass', { code: text, terminal: props.terminal })
    lane.value = openLanes.value[0]?.name || ''
    override.value = matching.value[0]?.name || ''
  } catch (e: any) {
    error.value = e.message
    code.value = ''
    await nextTick(); input.value?.focus()
  } finally { loading.value = false }
}

const openLanes = computed(() => props.lanes.filter((l) => result.value && l.direction === result.value.direction && l.status === 'Open'))
const matching = computed(() => props.overrides.filter((o) => result.value && o.override_type === 'Outside Slot Window' && (o.appointment === result.value.appointment)))
const blocked = computed(() => !!result.value?.blockers?.length)
const needsOverride = computed(() => !!result.value?.needs_override)
const canStart = computed(() => result.value && !blocked.value && lane.value && (!needsOverride.value || override.value))

async function start() {
  const r = result.value
  starting.value = true; error.value = ''
  try {
    await act('start_visit', { lane: lane.value, carrier: r.carrier, truck: r.truck, driver: r.driver, move_type: r.move_type, appointment: r.appointment, override: needsOverride.value ? override.value : '', container: r.container, booking_ref: r.booking_ref })
    emit('started'); emit('close')
  } catch (e: any) { error.value = e.message } finally { starting.value = false }
}

// ---- camera (needs https or localhost, and a browser that has BarcodeDetector) ----
async function startCam() {
  camError.value = ''
  const BD = (window as any).BarcodeDetector
  if (!BD) { camError.value = 'This browser cannot read QR codes from the camera. Use a handheld scanner, or type the code.'; return }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    camOn.value = true
    await nextTick()
    video.value!.srcObject = stream
    await video.value!.play()
    const det = new BD({ formats: ['qr_code'] })
    let last = 0
    const loop = async (t: number) => {
      if (!camOn.value) return
      if (t - last > 250) {
        last = t
        try { const codes = await det.detect(video.value!); if (codes[0]?.rawValue) { const v = codes[0].rawValue; stopCam(); code.value = v; lookup(v); return } } catch {}
      }
      timer = requestAnimationFrame(loop)
    }
    timer = requestAnimationFrame(loop)
  } catch (e: any) { camError.value = 'The camera could not be opened: ' + (e.message || e.name); stopCam() }
}
function stopCam() {
  camOn.value = false
  cancelAnimationFrame(timer)
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
}
const windowText = computed(() => {
  const w = result.value?.window
  if (!w) return ''
  return w.state === 'ok' ? `On time (window ${w.opens}–${w.closes})` : w.state === 'early' ? `${w.minutes} min too early (opens ${w.opens})` : `${w.minutes} min too late (closed ${w.closes})`
})
</script>

<template>
  <Modal :open="open" title="Scan gate pass" :hide-confirm="!result" confirm-label="Start visit" :loading="starting" :error="error" wide @close="$emit('close')" @confirm="canStart && start()">
    <template v-if="!result">
      <Field label="Pass code" hint="Scan with a handheld scanner, or type the short code printed under the QR.">
        <div class="flex gap-2">
          <input ref="input" v-model="code" class="tos-input font-mono" placeholder="Scan or type…" autocomplete="off" autocapitalize="off" @keydown.enter.prevent="lookup()" />
          <Button variant="solid" label="Look up" :loading="loading" @click="lookup()" />
        </div>
      </Field>
      <div>
        <Button v-if="!camOn" icon-left="lucide-camera" label="Use camera" @click="startCam" />
        <div v-else class="space-y-2">
          <video ref="video" class="aspect-video w-full rounded-5 bg-black object-cover" playsinline muted />
          <Button label="Stop camera" @click="stopCam" />
        </div>
        <p v-if="camError" class="mt-2 text-sm text-ink-amber-3">{{ camError }}</p>
      </div>
    </template>

    <template v-else>
      <div class="rounded-5 border border-outline-gray-1 p-3">
        <div class="flex items-start justify-between gap-2">
          <div><p class="text-base-medium text-ink-gray-9">{{ result.truck }} · {{ result.move_type }}</p><p class="text-sm text-ink-gray-5">{{ result.carrier_name || result.carrier }} · {{ result.driver_name || result.driver }}</p></div>
          <Badge theme="blue" :label="'Gate ' + result.direction" />
        </div>
        <p class="mt-2 text-sm text-ink-gray-6">{{ result.appointment }} · slot {{ result.slot_start }}–{{ result.slot_end }}<template v-if="result.container"> · {{ result.container }}</template><template v-if="result.booking_ref"> · {{ result.booking_ref }}</template></p>
        <p :class="['mt-2 text-sm font-medium', result.window.state === 'ok' ? 'text-ink-green-3' : 'text-ink-amber-3']">{{ windowText }}</p>
      </div>

      <ul v-if="blocked" class="space-y-1 rounded-5 bg-surface-red-1 p-3 text-sm text-ink-red-3">
        <li v-for="b in result.blockers" :key="b">{{ b }}</li>
        <li class="text-xs">These cannot be overridden. Send the truck to a supervisor.</li>
      </ul>

      <template v-else>
        <Field label="Lane">
          <select v-model="lane" class="tos-input"><option v-for="l in openLanes" :key="l.name" :value="l.name">Lane {{ l.lane_code }}</option></select>
          <p v-if="!openLanes.length" class="mt-1 text-sm text-ink-amber-3">No open Gate {{ result.direction }} lane right now.</p>
        </Field>
        <Field v-if="needsOverride" label="Approved override" :hint="matching.length ? 'This truck is outside its slot window, so an approved override is needed.' : undefined">
          <select v-model="override" class="tos-input"><option value="">Choose…</option><option v-for="o in matching" :key="o.name" :value="o.name">{{ o.name }} · valid until {{ String(o.valid_until).slice(11, 16) }}</option></select>
          <p v-if="!matching.length" class="mt-1 text-sm text-ink-amber-3">No approved override for {{ result.appointment }}. A clerk can request one under Appointments → Request override, then a supervisor approves it.</p>
        </Field>
      </template>
      <Button label="Scan another" @click="reset(); $nextTick(() => input?.focus())" />
    </template>
  </Modal>
</template>
