<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, PageHeader, PageHeaderTitle, useColorScheme } from 'frappe-ui'
import { useRouter } from 'vue-router'
import Modal from '../components/Modal.vue'
import DesignCanvas from '../yard/DesignCanvas.vue'
import { YardScene, type Snapshot } from '../yard/yard3d'
import type { YardLayout } from '../yard/layoutRender'
import { BASE_SURFACES, DRAW_KINDS, FACING, History, KINDS, SHAPEABLE, SURFACES, blockEnrich, centroid, facingName, hasFront, kindOf, minPoints, norm, plain, pointsOf, polygonal, setPoints, sizeOf, toShape, uid, type Backdrop, type DBlock, type DItem, type DrawKind } from '../yard/designerModel'
import { call, tos } from '../api'
import { layoutBounds } from '../yard/layoutRender'
import { useTerminal } from '../composables/useTerminal'

const { selected: terminal } = useTerminal()
const { resolvedColorScheme } = useColorScheme()
const router = useRouter()
const api = (name: string, params: Record<string, unknown> = {}, post = false) => call(`tos_next.api_layout.${name}`, params, { post })

// ---------- state ----------
const loading = ref(true)
const error = ref('')
const info = ref('')
const draft = ref('')
const modified = ref('')
const canPublish = ref(false)
const liveVersion = ref(0)
const blocks = ref<DBlock[]>([])
const geometry = ref({ slot: 6.4, row: 3.2, tier: 2.7, block_gap: 16, car_bay: 2.5, truck_bay: 4 })
const baseSurface = ref('Default')
const items = ref<DItem[]>([])
const selected = ref<string[]>([])
const snapSize = ref(1)
const mode = ref<'split' | 'plan' | '3d'>('split')
const canvas = ref<InstanceType<typeof DesignCanvas>>()
const history = new History()
const tool = ref<'select' | 'draw' | 'calibrate'>('select')
const drawKind = ref<DrawKind | null>(null)
const vertexIdx = ref(-1)
const backdrop = ref<Backdrop>({ image: '', x: 0, z: 0, width: 0, rotation: 0, opacity: 50 })
const bdAspect = ref(0.75)
const backdropEdit = ref(false)
const backdropHeight = computed(() => backdrop.value.width * bdAspect.value)
const previewing = ref<{ name: string; version: number; layout: any } | null>(null)
const histTick = ref(0) // makes undo/redo buttons react

const only = computed(() => (selected.value.length === 1 ? items.value.find((i) => i.uid === selected.value[0]) || null : null))
const unplaced = computed(() => blocks.value.filter((b) => !items.value.some((i) => i.item_type === 'Block' && i.yard_block === b.name)))
const groups = computed(() => {
  const out: Record<string, typeof KINDS> = {}
  for (const k of KINDS) (out[k.group] ||= []).push(k)
  return out
})
const locked = computed(() => !!only.value?.locked)

// ---------- load and save ----------
const key = () => JSON.stringify(items.value) + '|' + baseSurface.value + '|' + JSON.stringify(backdrop.value)
let savedKey = ''
const saveState = ref<'saved' | 'dirty' | 'saving' | 'error' | 'conflict'>('saved')
let saveTimer: ReturnType<typeof setTimeout>
let saving: Promise<void> | null = null

async function load() {
  if (!terminal.value) return
  loading.value = true
  error.value = ''
  try {
    const d: any = await api('designer_data', { terminal: terminal.value }, true)
    draft.value = d.draft
    modified.value = d.modified
    canPublish.value = d.can_publish
    liveVersion.value = d.live_version
    blocks.value = d.blocks
    geometry.value = d.geometry
    baseSurface.value = d.base_surface
    backdrop.value = d.backdrop
    measureBackdrop()
    previewing.value = null
    tool.value = 'select'
    vertexIdx.value = -1
    items.value = d.items.map((r: any) => ({ ...r, uid: uid() }))
    selected.value = []
    savedKey = key()
    saveState.value = 'saved'
    history.reset(JSON.stringify(items.value))
    histTick.value++
    await loadPreview()
    await nextTick()
    canvas.value?.fit()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function scheduleSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flush, 1200)
}
async function flush() {
  clearTimeout(saveTimer)
  if (saving) await saving
  if (key() === savedKey || !draft.value || saveState.value === 'conflict') return
  saving = doSave()
  await saving
  saving = null
}
async function doSave() {
  const k = key()
  saveState.value = 'saving'
  try {
    const r: any = await api('save_draft', { layout: draft.value, items: items.value.map(plain), base_surface: baseSurface.value, backdrop: backdrop.value, modified: modified.value }, true)
    modified.value = r.modified
    savedKey = k
    saveState.value = key() === savedKey ? 'saved' : 'dirty'
    if (saveState.value === 'dirty') scheduleSave()
    error.value = ''
  } catch (e: any) {
    saveState.value = /changed by someone else/.test(e.message) ? 'conflict' : 'error'
    error.value = e.message
  }
}
function markDirty() {
  if (key() !== savedKey && saveState.value !== 'conflict') { saveState.value = 'dirty'; scheduleSave() }
  schedulePreview()
}

/** Call after any finished change: records an undo step and queues a save. */
function commit() {
  if (history.push(JSON.stringify(items.value))) histTick.value++
  markDirty()
}
watch(baseSurface, () => markDirty())
watch(backdrop, () => markDirty(), { deep: true })
function applyHistory(state: string | null) {
  if (!state) return
  items.value = JSON.parse(state)
  selected.value = selected.value.filter((u) => items.value.some((i) => i.uid === u))
  histTick.value++
  markDirty()
}
const undo = () => applyHistory(history.undo())
const redo = () => applyHistory(history.redo())
const canUndo = computed(() => (histTick.value, history.canUndo))
const canRedo = computed(() => (histTick.value, history.canRedo))

// ---------- editing ----------
function centrePoint() {
  const c = canvas.value?.centre() || { x: 0, z: 0 }
  const s = snapSize.value
  return s > 0 ? { x: Math.round(c.x / s) * s, z: Math.round(c.z / s) * s } : c
}
function addKind(type: string, x?: number, z?: number) {
  const k = kindOf(type)!
  const p = x === undefined ? centrePoint() : { x, z: z! }
  const it: DItem = { uid: uid(), item_type: type, shape: 'Rectangle', x: p.x, z: p.z!, rotation: 0, length: k.length, width: k.width, height: k.height, surface: k.surface || '', label: '', direction: 'Two-way', locked: 0 }
  items.value.push(it)
  selected.value = [it.uid]
  commit()
}
function addBlock(name: string, x?: number, z?: number) {
  const p = x === undefined ? centrePoint() : { x, z: z! }
  const it: DItem = { uid: uid(), item_type: 'Block', yard_block: name, shape: 'Rectangle', x: p.x, z: p.z!, rotation: 0, door_side: 'Lower bay end', locked: 0 }
  items.value.push(it)
  selected.value = [it.uid]
  commit()
}
function onDrop(payload: { kind: string; id: string }, x: number, z: number) {
  if (payload.kind === 'block') addBlock(payload.id, x, z)
  else addKind(payload.id, x, z)
}
function remove() {
  const gone = new Set(items.value.filter((i) => selected.value.includes(i.uid) && !i.locked).map((i) => i.uid))
  if (!gone.size) return
  items.value = items.value.filter((i) => !gone.has(i.uid))
  selected.value = selected.value.filter((u) => !gone.has(u))
  commit()
}
function duplicate() {
  const copies: DItem[] = []
  for (const it of items.value.filter((i) => selected.value.includes(i.uid) && i.item_type !== 'Block')) {
    copies.push({ ...JSON.parse(JSON.stringify(it)), uid: uid(), x: (it.x || 0) + 6, z: (it.z || 0) + 6, locked: 0 })
  }
  if (!copies.length) return
  items.value.push(...copies)
  selected.value = copies.map((c) => c.uid)
  commit()
}
function rotateBy(deg: number) {
  for (const it of items.value) if (selected.value.includes(it.uid) && !it.locked) it.rotation = norm((it.rotation || 0) + deg)
  commit()
}
function face(rotation: number) {
  if (!only.value || only.value.locked) return
  only.value.rotation = rotation
  commit()
}
function nudge(dx: number, dz: number) {
  const step = snapSize.value > 0 ? snapSize.value : 1
  for (const it of items.value) if (selected.value.includes(it.uid) && !it.locked) { it.x = (it.x || 0) + dx * step; it.z = (it.z || 0) + dz * step }
  commit()
}
function toggleLock() {
  if (!only.value) return
  only.value.locked = only.value.locked ? 0 : 1
  commit()
}

// ---------- shapes drawn by points ----------
function startDraw(k: DrawKind) {
  backdropEdit.value = false
  drawKind.value = k
  tool.value = 'draw'
  selected.value = []
  info.value = ''
}
function cancelTool() {
  canvas.value?.cancelDraw()
  tool.value = 'select'
  drawKind.value = null
}
function onDrawn(pts: [number, number][]) {
  const k = drawKind.value
  if (!k || pts.length < k.min) { info.value = `A ${k?.label.toLowerCase() || 'shape'} needs at least ${k?.min} points.`; return }
  const c = centroid(pts)
  const it: DItem = {
    uid: uid(), item_type: k.type, shape: k.shape, x: c.x, z: c.z, rotation: 0, length: 0, width: k.type === 'Road' ? 12 : k.type === 'Fence' ? 0.4 : 0,
    height: k.type === 'Building' ? 8 : k.type === 'Fence' ? 2.4 : 0, surface: k.type === 'Ground' ? 'Concrete' : k.type === 'Road' ? 'Asphalt' : '', label: '', direction: 'Two-way', locked: 0,
  }
  setPoints(it, pts)
  items.value.push(it)
  tool.value = 'select'
  drawKind.value = null
  selected.value = [it.uid]
  commit()
}
function editAsShape() {
  if (!only.value || only.value.locked) return
  if (toShape(only.value, blocks.value)) { vertexIdx.value = -1; commit() }
}
function deleteVertex() {
  const it = only.value
  if (!it || vertexIdx.value < 0 || it.locked) return
  const pts = pointsOf(it)
  if (pts.length <= minPoints(it)) { info.value = `A ${it.shape?.toLowerCase()} needs at least ${minPoints(it)} points. Delete the whole item instead.`; return }
  pts.splice(vertexIdx.value, 1)
  setPoints(it, pts)
  vertexIdx.value = -1
  commit()
}

// ---------- backdrop picture ----------
const bd = ref({ open: false, loading: false, error: '' })
const fileInput = ref<HTMLInputElement>()
const cal = ref({ open: false, a: [0, 0] as [number, number], b: [0, 0] as [number, number], metres: '' as string | number, error: '' })
function measureBackdrop() {
  if (!backdrop.value.image) return
  const img = new Image()
  img.onload = () => { if (img.naturalWidth) bdAspect.value = img.naturalHeight / img.naturalWidth }
  img.src = backdrop.value.image
}
async function uploadBackdrop(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  bd.value.loading = true
  bd.value.error = ''
  try {
    await flush()
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('is_private', '1')
    form.append('doctype', 'Yard Layout')
    form.append('docname', draft.value)
    const res = await fetch('/api/method/upload_file', { method: 'POST', credentials: 'same-origin', headers: { 'X-Frappe-CSRF-Token': (window as any).csrf_token || '' }, body: form })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.exception || data?.message || 'The upload failed')
    const url: string = data.message.file_url
    const box = layoutBounds(items.value.map((i) => blockEnrich(i, blocks.value)).filter(Boolean) as any[])
    const c = box.isEmpty() ? { x: 0, z: 0 } : { x: (box.min.x + box.max.x) / 2, z: (box.min.z + box.max.z) / 2 }
    backdrop.value = { image: url, x: Math.round(c.x), z: Math.round(c.z), width: backdrop.value.width || 200, rotation: 0, opacity: 55 }
    measureBackdrop()
    info.value = 'Picture added. Next, set its scale: click two points that are a known distance apart on the picture.'
  } catch (e: any) { bd.value.error = e.message } finally { bd.value.loading = false }
}
function startCalibrate() {
  bd.value.open = false
  backdropEdit.value = false
  tool.value = 'calibrate'
  info.value = 'Click one end of a distance you know on the picture, then the other end.'
}
function onCalibrated(a: [number, number], b: [number, number]) {
  tool.value = 'select'
  info.value = ''
  cal.value = { open: true, a, b, metres: '', error: '' }
}
function applyScale() {
  const m = Number(cal.value.metres)
  const d = Math.hypot(cal.value.b[0] - cal.value.a[0], cal.value.b[1] - cal.value.a[1])
  if (!(m > 0) || d < 0.01) { cal.value.error = 'Enter the real distance in metres.'; return }
  const f = m / d
  const [ax, az] = cal.value.a
  const bk = backdrop.value
  backdrop.value = { ...bk, width: Math.round(bk.width * f * 100) / 100, x: Math.round((ax + f * (bk.x - ax)) * 100) / 100, z: Math.round((az + f * (bk.z - az)) * 100) / 100 }
  cal.value.open = false
}
function removeBackdrop() {
  backdrop.value = { image: '', x: 0, z: 0, width: 0, rotation: 0, opacity: 50 }
  backdropEdit.value = false
}

// ---------- history ----------
const hist = ref({ open: false, loading: false, error: '', rows: [] as any[], busy: '' })
async function openHistory() {
  hist.value = { open: true, loading: true, error: '', rows: [], busy: '' }
  try { await flush(); hist.value.rows = (await api('layout_history', { terminal: terminal.value })) as any[] } catch (e: any) { hist.value.error = e.message } finally { hist.value.loading = false }
}
async function previewVersion(r: any) {
  hist.value.busy = r.name
  try {
    const layout: any = await api('layout_view', { layout: r.name })
    previewing.value = { name: r.layout_name || r.name, version: r.version, layout }
    hist.value.open = false
    mode.value = mode.value === 'plan' ? 'split' : mode.value
    drawPreview()
    scene?.fit()
  } catch (e: any) { hist.value.error = e.message } finally { hist.value.busy = '' }
}
function endPreview() { previewing.value = null; drawPreview() }
async function restore(r: any) {
  hist.value.busy = r.name
  try {
    await api('restore_version', { layout: r.name, replace: 1 }, true)
    hist.value.open = false
    saveState.value = 'saved'
    info.value = `Version ${r.version || ''} is now your draft. Publish it when you are happy with it.`
    await load()
  } catch (e: any) { hist.value.error = e.message } finally { hist.value.busy = '' }
}

function onKey(ev: KeyboardEvent) {
  const t = ev.target as HTMLElement
  if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return
  const mod = ev.ctrlKey || ev.metaKey
  const k = ev.key.toLowerCase()
  if (mod && k === 'z') { ev.preventDefault(); ev.shiftKey ? redo() : undo() }
  else if (mod && k === 'y') { ev.preventDefault(); redo() }
  else if (mod && k === 'd') { ev.preventDefault(); duplicate() }
  else if (k === 'enter' && tool.value === 'draw') { ev.preventDefault(); canvas.value?.finishDraw() }
  else if (k === 'escape' && tool.value !== 'select') cancelTool()
  else if ((k === 'delete' || k === 'backspace') && vertexIdx.value >= 0) { ev.preventDefault(); deleteVertex() }
  else if (k === 'delete' || k === 'backspace') { ev.preventDefault(); remove() }
  else if (k === 'escape') { selected.value = []; vertexIdx.value = -1 }
  else if (k === 'r' && !mod) rotateBy(ev.shiftKey ? -90 : 90)
  else if (k.startsWith('arrow') && selected.value.length) {
    ev.preventDefault()
    const m = ev.shiftKey ? 5 : 1
    nudge(k === 'arrowleft' ? -m : k === 'arrowright' ? m : 0, k === 'arrowup' ? -m : k === 'arrowdown' ? m : 0)
  }
}

// ---------- palette drag ----------
function dragStart(ev: DragEvent, kind: string, id: string) {
  ev.dataTransfer?.setData('application/x-tos', JSON.stringify({ kind, id }))
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'copy'
}

// ---------- 3D preview ----------
const host = ref<HTMLElement>()
let scene: YardScene | null = null
let snapshot: Snapshot | null = null
let previewTimer: ReturnType<typeof setTimeout>
async function loadPreview() {
  try { snapshot = (await tos('yard_snapshot', { terminal: terminal.value })) as Snapshot } catch (e: any) { error.value = e.message }
  drawPreview()
}
function schedulePreview() {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(drawPreview, 150)
}
function drawPreview() {
  if (!scene || !snapshot) return
  if (previewing.value) { scene.setData({ ...snapshot, layout: previewing.value.layout }); return }
  const layout: YardLayout = {
    name: draft.value, version: 0, base_surface: baseSurface.value, automatic: false, geometry: geometry.value,
    items: items.value.map((i) => blockEnrich(i, blocks.value)).filter(Boolean) as any[],
  }
  scene.setData({ ...snapshot, layout })
}
watch(resolvedColorScheme, (v) => scene?.setTheme(v === 'dark' ? 'dark' : 'light'))
watch(mode, async () => { await nextTick(); canvas.value?.fit() })
watch(terminal, async (_n, old) => { if (old) await flush(); selected.value = []; load() })

// ---------- publish and discard ----------
const pub = ref({ open: false, loading: false, error: '', problems: [] as string[] })
const summary = computed(() => {
  const n: Record<string, number> = {}
  for (const i of items.value) n[i.item_type] = (n[i.item_type] || 0) + 1
  return Object.entries(n).map(([k, v]) => `${v} × ${kindOf(k)?.label || k}`).join(', ') || 'nothing yet'
})
async function openPublish() {
  pub.value = { open: true, loading: true, error: '', problems: [] }
  try {
    await flush()
    if (saveState.value === 'error' || saveState.value === 'conflict') throw new Error(error.value)
    pub.value.problems = (await api('check_draft', { layout: draft.value })) as string[]
  } catch (e: any) { pub.value.error = e.message } finally { pub.value.loading = false }
}
async function doPublish() {
  pub.value.loading = true
  pub.value.error = ''
  try {
    await api('publish_draft', { layout: draft.value }, true)
    pub.value.open = false
    info.value = 'Published. The 3D yard now uses this layout. Further changes go into a new draft.'
    await load()
  } catch (e: any) { pub.value.error = e.message } finally { pub.value.loading = false }
}
const disc = ref({ open: false, loading: false, error: '' })
async function doDiscard() {
  disc.value.loading = true
  try {
    await api('discard_draft', { layout: draft.value }, true)
    disc.value.open = false
    saveState.value = 'saved'
    info.value = 'Draft discarded. This is a fresh copy of the live layout.'
    await load()
  } catch (e: any) { disc.value.error = e.message } finally { disc.value.loading = false }
}

function beforeUnload(ev: BeforeUnloadEvent) {
  if (saveState.value !== 'saved') { ev.preventDefault(); ev.returnValue = '' }
}
onMounted(() => {
  scene = new YardScene(host.value!, { onPick: () => {}, onHover: () => {} })
  scene.setTheme(resolvedColorScheme.value === 'dark' ? 'dark' : 'light')
  window.addEventListener('keydown', onKey)
  window.addEventListener('beforeunload', beforeUnload)
  load()
})
onBeforeUnmount(() => {
  flush()
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('beforeunload', beforeUnload)
  clearTimeout(saveTimer); clearTimeout(previewTimer)
  scene?.dispose(); scene = null
})

const statusText = computed(() => ({ saved: 'All changes saved', dirty: 'Unsaved changes…', saving: 'Saving…', error: 'Could not save', conflict: 'Draft changed elsewhere' })[saveState.value])
const field = (it: DItem, f: string) => {
  const t = it.item_type
  switch (f) {
    case 'label': return t !== 'Block'
    case 'size': return t !== 'Block' && t !== 'Tree' && t !== 'Light Mast'
    case 'height': return ['Building', 'Gate', 'Heap', 'Crane', 'Fence', 'Light Mast', 'Tree', 'Weighbridge'].includes(t)
    case 'surface': return ['Ground', 'Road', 'Car Park', 'Truck Park'].includes(t)
    case 'direction': return t === 'Road'
    case 'colour': return t !== 'Block'
    default: return false
  }
}
const lengthLabel = (t: string) => (t === 'Crane' ? 'Length (along the quay)' : 'Length')
const widthLabel = (t: string) => (t === 'Rail Track' ? 'Gauge' : t === 'Crane' ? 'Span' : t === 'Tree' ? 'Crown width' : 'Width')
const blockOf = (it: DItem) => blocks.value.find((b) => b.name === it.yard_block)
</script>

<template>
  <PageHeader>
    <PageHeaderTitle title="Yard Designer" />
    <div class="flex flex-wrap items-center gap-2">
      <span :class="['text-sm', saveState === 'error' || saveState === 'conflict' ? 'text-ink-red-3' : 'text-ink-gray-5']" role="status">{{ statusText }}</span>
      <Button icon="lucide-undo-2" tooltip="Undo (Ctrl+Z)" aria-label="Undo" :disabled="!canUndo" @click="undo" />
      <Button icon="lucide-redo-2" tooltip="Redo (Ctrl+Y)" aria-label="Redo" :disabled="!canRedo" @click="redo" />
      <label class="flex items-center gap-1 text-sm text-ink-gray-6">
        Snap
        <select v-model.number="snapSize" class="tos-input !w-auto !py-1" aria-label="Snap to grid">
          <option :value="0">Off</option><option :value="0.5">0.5 m</option><option :value="1">1 m</option><option :value="5">5 m</option>
        </select>
      </label>
      <label class="flex items-center gap-1 text-sm text-ink-gray-6">
        Ground
        <select v-model="baseSurface" class="tos-input !w-auto !py-1" aria-label="Ground surface">
          <option v-for="s in BASE_SURFACES" :key="s">{{ s }}</option>
        </select>
      </label>
      <div class="flex overflow-hidden rounded-4 border border-outline-gray-2" role="group" aria-label="View">
        <button v-for="m in [['split', 'Both'], ['plan', 'Plan'], ['3d', '3D']]" :key="m[0]" :aria-pressed="mode === m[0]" :class="['px-2.5 py-1 text-sm', mode === m[0] ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-6']" @click="mode = m[0] as any">{{ m[1] }}</button>
      </div>
      <Button icon="lucide-image" tooltip="Backdrop picture to trace over" aria-label="Backdrop picture" @click="bd = { open: true, loading: false, error: '' }" />
      <Button icon="lucide-history" tooltip="Layout history" aria-label="Layout history" @click="openHistory" />
      <Button label="Discard draft" @click="disc = { open: true, loading: false, error: '' }" />
      <Button variant="solid" label="Publish…" :disabled="!canPublish" :tooltip="canPublish ? '' : 'Only a Terminal Admin can publish'" @click="openPublish" />
    </div>
  </PageHeader>

  <div class="flex h-[calc(100vh-3.5rem)] min-h-[560px] flex-col lg:flex-row">
    <!-- palette and inspector -->
    <aside class="flex max-h-[45vh] w-full shrink-0 flex-col overflow-y-auto border-b border-outline-gray-1 bg-surface-white lg:max-h-none lg:w-72 lg:border-b-0 lg:border-r">
      <div class="space-y-4 p-3">
        <section v-if="unplaced.length">
          <p class="mb-1.5 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-ink-amber-3">Blocks not placed <Badge theme="orange" :label="String(unplaced.length)" /></p>
          <div class="flex flex-wrap gap-1.5">
            <button v-for="b in unplaced" :key="b.name" draggable="true" class="rounded-4 border border-outline-amber-2 bg-surface-amber-1 px-2.5 py-1.5 text-sm text-ink-gray-8" :title="`${b.bay_count} bays × ${b.row_count} rows. Drag onto the plan or click to add.`" @dragstart="dragStart($event, 'block', b.name)" @click="addBlock(b.name)">
              Block {{ b.block_code }}
            </button>
          </div>
        </section>
        <section>
          <p class="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Draw by points</p>
          <div class="grid grid-cols-2 gap-1.5">
            <button v-for="k in DRAW_KINDS" :key="k.id" :aria-pressed="tool === 'draw' && drawKind?.id === k.id" :class="['flex items-center gap-2 rounded-4 border px-2 py-1.5 text-left text-sm text-ink-gray-8 hover:bg-surface-gray-2', tool === 'draw' && drawKind?.id === k.id ? 'border-outline-gray-4 bg-surface-gray-3' : 'border-outline-gray-2']" :title="k.hint" @click="startDraw(k)">
              <span :class="[k.icon, 'size-4 shrink-0']" aria-hidden="true" />{{ k.label }}
            </button>
          </div>
        </section>
        <section v-for="(list, g) in groups" :key="g">
          <p class="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ g }}</p>
          <div class="grid grid-cols-2 gap-1.5">
            <button v-for="k in list" :key="k.type" draggable="true" class="flex items-center gap-2 rounded-4 border border-outline-gray-2 px-2 py-1.5 text-left text-sm text-ink-gray-8 hover:bg-surface-gray-2" :title="k.hint + ' Drag onto the plan or click to add.'" @dragstart="dragStart($event, 'type', k.type)" @click="addKind(k.type)">
              <span :class="[k.icon, 'size-4 shrink-0']" aria-hidden="true" />{{ k.label }}
            </button>
          </div>
        </section>
      </div>

      <div class="mt-auto border-t border-outline-gray-1 p-3">
        <p class="mb-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Selected</p>
        <p v-if="!selected.length" class="text-sm text-ink-gray-5">Click something on the plan, or add it from above. Drag to move, use the corner squares to resize and the round handle to rotate. Shift-click selects several.</p>
        <div v-else-if="!only" class="space-y-2">
          <p class="text-sm text-ink-gray-7">{{ selected.length }} items selected</p>
          <div class="flex flex-wrap gap-1.5">
            <Button label="Turn 90°" icon-left="lucide-rotate-cw" @click="rotateBy(90)" />
            <Button label="Duplicate" icon-left="lucide-copy" @click="duplicate" />
            <Button label="Delete" icon-left="lucide-trash-2" theme="red" @click="remove" />
          </div>
        </div>
        <div v-else class="space-y-3 text-sm">
          <p class="font-medium text-ink-gray-9">{{ only.item_type === 'Block' ? `Block ${blockOf(only)?.block_code || ''}` : kindOf(only.item_type)?.label || only.item_type }}</p>
          <div v-if="polygonal(only)" class="space-y-1.5">
            <p class="text-ink-gray-6">{{ pointsOf(only).length }} points. Drag a point to move it, double-click an edge to add one, or click a point and press Delete to remove it.</p>
            <Button v-if="vertexIdx >= 0" label="Delete this point" icon-left="lucide-minus-circle" :disabled="locked" @click="deleteVertex" />
          </div>
          <Button v-else-if="SHAPEABLE[only.item_type]" label="Edit by points" icon-left="lucide-pentagon" :disabled="locked" @click="editAsShape" />
          <p v-if="locked" class="text-ink-gray-5">Locked: unlock to move or change it.</p>

          <label v-if="field(only, 'label')" class="block"><span class="text-ink-gray-6">Name shown in 3D</span>
            <input v-model="only.label" class="tos-input mt-1" :disabled="locked" @change="commit" />
          </label>

          <div v-if="!polygonal(only)" class="grid grid-cols-2 gap-2">
            <label><span class="text-ink-gray-6">East–west (X)</span><input v-model.number="only.x" type="number" step="0.5" class="tos-input mt-1" :disabled="locked" @change="commit" /></label>
            <label><span class="text-ink-gray-6">North–south (Z)</span><input v-model.number="only.z" type="number" step="0.5" class="tos-input mt-1" :disabled="locked" @change="commit" /></label>
            <label class="col-span-2"><span class="text-ink-gray-6">Rotation (degrees clockwise)</span><input v-model.number="only.rotation" type="number" step="5" class="tos-input mt-1" :disabled="locked" @change="only.rotation = norm(only.rotation || 0); commit()" /></label>
          </div>
          <div v-if="!polygonal(only)" class="flex flex-wrap gap-1.5">
            <Button label="−90°" :disabled="locked" @click="rotateBy(-90)" /><Button label="+90°" :disabled="locked" @click="rotateBy(90)" /><Button label="180°" :disabled="locked" @click="rotateBy(180)" />
          </div>

          <div v-if="hasFront(only.item_type)">
            <p class="text-ink-gray-6">{{ only.item_type === 'Gate' ? 'Trucks drive toward' : 'Entrance faces' }} <b class="text-ink-gray-9">{{ facingName(only.rotation || 0) || 'a custom angle' }}</b></p>
            <div class="mt-1 grid grid-cols-4 gap-1">
              <button v-for="f in FACING" :key="f.label" :disabled="locked" :aria-pressed="facingName(only.rotation || 0) === f.label" :class="['rounded-4 border px-1 py-1 text-xs', facingName(only.rotation || 0) === f.label ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-7']" @click="face(f.rotation)">{{ f.label }}</button>
            </div>
            <p class="mt-1 text-xs text-ink-gray-5">{{ only.item_type === 'Gate' ? 'The arrows on the plan show the way trucks drive in; the barriers are on the opposite end.' : 'The red mark on the plan is the entrance.' }}</p>
          </div>

          <label v-if="only.item_type === 'Block'" class="block"><span class="text-ink-gray-6">Container doors face</span>
            <select v-model="only.door_side" class="tos-input mt-1" :disabled="locked" @change="commit"><option>Lower bay end</option><option>Higher bay end</option></select>
            <span class="text-xs text-ink-gray-5">The orange edge on the plan is the door end.</span>
          </label>

          <label v-if="polygonal(only) && only.shape === 'Polyline' && only.item_type === 'Road'" class="block"><span class="text-ink-gray-6">Road width (m)</span><input v-model.number="only.width" type="number" min="1" step="0.5" class="tos-input mt-1" :disabled="locked" @change="commit" /></label>
          <div v-if="field(only, 'size') && !polygonal(only)" class="grid grid-cols-2 gap-2">
            <label><span class="text-ink-gray-6">{{ lengthLabel(only.item_type) }} (m)</span><input v-model.number="only.length" type="number" min="0.2" step="0.5" class="tos-input mt-1" :disabled="locked" @change="commit" /></label>
            <label><span class="text-ink-gray-6">{{ widthLabel(only.item_type) }} (m)</span><input v-model.number="only.width" type="number" min="0.2" step="0.5" class="tos-input mt-1" :disabled="locked" @change="commit" /></label>
          </div>
          <p v-if="only.item_type === 'Block'" class="text-xs text-ink-gray-5">Size follows the block's bays and rows: {{ sizeOf(only, blocks).l.toFixed(1) }} × {{ sizeOf(only, blocks).w.toFixed(1) }} m.</p>
          <label v-if="field(only, 'height')" class="block"><span class="text-ink-gray-6">Height (m)</span><input v-model.number="only.height" type="number" min="0" step="0.5" class="tos-input mt-1" :disabled="locked" @change="commit" /></label>
          <label v-if="field(only, 'surface')" class="block"><span class="text-ink-gray-6">Surface</span>
            <select v-model="only.surface" class="tos-input mt-1" :disabled="locked" @change="commit"><option v-for="s in SURFACES" :key="s">{{ s }}</option></select>
          </label>
          <label v-if="field(only, 'direction')" class="block"><span class="text-ink-gray-6">Traffic</span>
            <select v-model="only.direction" class="tos-input mt-1" :disabled="locked" @change="commit"><option>Two-way</option><option>One-way forward</option><option>One-way reverse</option></select>
          </label>
          <div v-if="field(only, 'colour')" class="flex items-center gap-2">
            <label class="text-ink-gray-6" for="col">Colour</label>
            <input id="col" type="color" :value="only.colour || '#94a3b8'" :disabled="locked" class="h-7 w-10 rounded border border-outline-gray-2" @input="only.colour = ($event.target as HTMLInputElement).value" @change="commit" />
            <Button v-if="only.colour" label="Reset" variant="ghost" :disabled="locked" @click="only.colour = ''; commit()" />
          </div>

          <div class="flex flex-wrap gap-1.5 pt-1">
            <Button :label="locked ? 'Unlock' : 'Lock'" :icon-left="locked ? 'lucide-lock-open' : 'lucide-lock'" @click="toggleLock" />
            <Button v-if="only.item_type !== 'Block'" label="Duplicate" icon-left="lucide-copy" @click="duplicate" />
            <Button :label="only.item_type === 'Block' ? 'Remove from layout' : 'Delete'" icon-left="lucide-trash-2" theme="red" :disabled="locked" @click="remove" />
          </div>
        </div>
      </div>
    </aside>

    <!-- plan and preview -->
    <div class="relative grid min-h-0 flex-1 grid-cols-1 gap-px bg-outline-gray-1" :class="mode === 'split' ? 'lg:grid-cols-2' : ''">
      <section v-show="mode !== '3d'" class="relative min-h-[300px] overflow-hidden bg-surface-gray-2" aria-label="Plan editor">
        <DesignCanvas
          ref="canvas" :items="items" :blocks="blocks" :selected="selected" :snap="snapSize" :geometry="geometry" :tool="tool" :draw-closed="drawKind?.shape === 'Polygon'" :draw-min="drawKind?.min || 2" :vertex="vertexIdx"
          :backdrop="backdrop" :backdrop-height="backdropHeight" :backdrop-edit="backdropEdit"
          @select="selected = $event" @commit="commit" @drop="onDrop" @drawn="onDrawn" @calibrated="onCalibrated" @vertex="vertexIdx = $event"
        />
        <div v-if="tool !== 'select'" class="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-3 rounded-5 border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-8 shadow-lg">
          <span v-if="tool === 'draw'">Click each point of the {{ drawKind?.label.toLowerCase() }}. Double-click or press Enter to finish.</span>
          <span v-else>Click two points on the picture a known distance apart.</span>
          <Button label="Cancel" @click="cancelTool" />
        </div>
        <div v-if="backdropEdit" class="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-3 rounded-5 border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-8 shadow-lg">
          <span>Drag the picture to move it.</span><Button label="Done" @click="backdropEdit = false" />
        </div>
        <div class="pointer-events-none absolute left-3 top-3 rounded-4 bg-surface-white/90 px-2 py-1 text-xs text-ink-gray-6 shadow-sm">Plan · north is up · scroll to zoom · drag empty space to pan · Shift-drag to select several</div>
        <div class="absolute bottom-3 left-3 flex gap-1.5">
          <Button icon="lucide-zoom-in" aria-label="Zoom in" @click="canvas?.zoomBy(1.3)" />
          <Button icon="lucide-zoom-out" aria-label="Zoom out" @click="canvas?.zoomBy(1 / 1.3)" />
          <Button label="Fit" icon-left="lucide-maximize" @click="canvas?.fit()" />
        </div>
      </section>
      <section v-show="mode !== 'plan'" class="relative min-h-[300px] overflow-hidden bg-surface-gray-2" aria-label="3D preview">
        <div ref="host" class="absolute inset-0" />
        <div v-if="!previewing" class="pointer-events-none absolute left-3 top-3 rounded-4 bg-surface-white/90 px-2 py-1 text-xs text-ink-gray-6 shadow-sm">3D preview of this draft · not live until published</div>
        <div v-else class="absolute left-3 top-3 flex items-center gap-2 rounded-5 border border-outline-amber-2 bg-surface-amber-1 px-3 py-1.5 text-sm text-ink-gray-8 shadow-sm">
          Previewing {{ previewing.version ? 'version ' + previewing.version : previewing.name }}, not your draft <Button label="Back to my draft" @click="endPreview" />
        </div>
        <div class="absolute bottom-3 left-3"><Button label="Re-centre" icon-left="lucide-crosshair" @click="scene?.fit()" /></div>
      </section>
      <div v-if="loading" class="absolute inset-0 z-10 flex items-center justify-center bg-surface-base/60 text-sm text-ink-gray-6">Loading the draft…</div>
    </div>
  </div>

  <div v-if="error || info" class="fixed bottom-4 left-1/2 z-40 max-w-xl -translate-x-1/2 space-y-2">
    <div v-if="error" class="flex items-start gap-3 rounded-5 border border-outline-red-2 bg-surface-white px-3 py-2 shadow-lg">
      <ErrorMessage class="flex-1" :message="error" />
      <Button v-if="saveState === 'conflict'" label="Reload" @click="error = ''; saveState = 'saved'; load()" />
      <Button v-else-if="saveState === 'error'" label="Retry" @click="error = ''; flush()" />
      <Button variant="ghost" icon="lucide-x" aria-label="Dismiss" @click="error = ''" />
    </div>
    <div v-if="info" class="flex items-center gap-3 rounded-5 border border-outline-green-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-lg">
      <span class="flex-1">{{ info }}</span>
      <Button label="View 3D Yard" @click="router.push('/yard')" />
      <Button variant="ghost" icon="lucide-x" aria-label="Dismiss" @click="info = ''" />
    </div>
  </div>

  <Modal :open="pub.open" title="Publish this layout" :confirm-label="pub.problems.length ? 'Cannot publish yet' : 'Publish now'" :loading="pub.loading" :error="pub.error" :hide-confirm="!!pub.problems.length" @close="pub.open = false" @confirm="doPublish">
    <template v-if="pub.problems.length">
      <p class="text-sm text-ink-gray-7">Fix these first:</p>
      <ul class="list-disc space-y-1 pl-5 text-sm text-ink-red-3"><li v-for="p in pub.problems" :key="p">{{ p }}</li></ul>
    </template>
    <template v-else-if="!pub.loading">
      <p class="text-sm text-ink-gray-7">This replaces the live yard layout (version {{ liveVersion }}). Everyone using the 3D yard sees the new layout straight away. The old layout is kept as Archived.</p>
      <p class="text-sm text-ink-gray-6">The draft has {{ summary }}.</p>
    </template>
  </Modal>
  <Modal :open="disc.open" title="Discard this draft?" confirm-label="Discard draft" :loading="disc.loading" :error="disc.error" @close="disc.open = false" @confirm="doDiscard">
    <p class="text-sm text-ink-gray-7">Everything changed since the last publish is thrown away and you start again from the live layout. The live yard is not affected.</p>
  </Modal>

  <Modal :open="bd.open" title="Backdrop picture" hide-confirm :error="bd.error" @close="bd.open = false">
    <p class="text-sm text-ink-gray-7">Put a site plan or aerial photo behind the plan and trace over it. It is only a guide: it does not appear in the 3D yard.</p>
    <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" class="hidden" @change="uploadBackdrop" />
    <div class="flex flex-wrap gap-2">
      <Button :label="backdrop.image ? 'Replace picture' : 'Choose a picture'" icon-left="lucide-upload" :loading="bd.loading" @click="fileInput?.click()" />
      <Button v-if="backdrop.image" label="Remove" icon-left="lucide-trash-2" theme="red" @click="removeBackdrop" />
    </div>
    <template v-if="backdrop.image">
      <div class="flex flex-wrap gap-2">
        <Button label="Set scale (two clicks)" icon-left="lucide-ruler" @click="startCalibrate" />
        <Button label="Move the picture" icon-left="lucide-move" @click="backdropEdit = true; bd.open = false" />
      </div>
      <label class="block text-sm"><span class="text-ink-gray-6">Opacity: {{ backdrop.opacity }}%</span><input v-model.number="backdrop.opacity" type="range" min="10" max="100" class="mt-1 w-full" /></label>
      <div class="grid grid-cols-2 gap-2 text-sm">
        <label><span class="text-ink-gray-6">Width on the site (m)</span><input v-model.number="backdrop.width" type="number" min="1" step="1" class="tos-input mt-1" /></label>
        <label><span class="text-ink-gray-6">Rotation (degrees)</span><input v-model.number="backdrop.rotation" type="number" step="1" class="tos-input mt-1" /></label>
        <label><span class="text-ink-gray-6">Centre east–west (m)</span><input v-model.number="backdrop.x" type="number" step="1" class="tos-input mt-1" /></label>
        <label><span class="text-ink-gray-6">Centre north–south (m)</span><input v-model.number="backdrop.z" type="number" step="1" class="tos-input mt-1" /></label>
      </div>
    </template>
  </Modal>
  <Modal :open="cal.open" title="How far apart are those two points?" confirm-label="Set scale" :error="cal.error" @close="cal.open = false" @confirm="applyScale">
    <p class="text-sm text-ink-gray-7">Enter the real distance in metres between the two points you clicked, for example the length of a known road or building.</p>
    <input v-model="cal.metres" type="number" min="0" step="0.1" class="tos-input" placeholder="Metres" aria-label="Real distance in metres" @keydown.enter.prevent="applyScale" />
  </Modal>
  <Modal :open="hist.open" title="Layout history" hide-confirm wide :error="hist.error" @close="hist.open = false">
    <p v-if="hist.loading" class="text-sm text-ink-gray-5">Loading…</p>
    <ul v-else class="divide-y divide-outline-gray-1 text-sm">
      <li v-for="r in hist.rows" :key="r.name" class="flex flex-wrap items-center gap-2 py-2">
        <div class="min-w-0 flex-1">
          <p class="truncate font-medium text-ink-gray-9">{{ r.status === 'Draft' ? 'Your draft' : 'Version ' + r.version }} <span class="font-normal text-ink-gray-5">· {{ r.layout_name }}</span></p>
          <p class="text-ink-gray-5">{{ r.status }} · {{ r.item_count }} items<template v-if="r.published_on"> · published {{ String(r.published_on).slice(0, 16) }} by {{ r.published_by }}</template></p>
        </div>
        <Badge :theme="r.status === 'Published' ? 'green' : r.status === 'Draft' ? 'orange' : 'gray'" :label="r.status" />
        <Button label="Preview in 3D" :loading="hist.busy === r.name" @click="previewVersion(r)" />
        <Button v-if="r.status !== 'Draft'" label="Restore as draft" :loading="hist.busy === r.name" @click="restore(r)" />
      </li>
    </ul>
    <p class="text-xs text-ink-gray-5">Restoring copies that version into your draft, replacing the draft you have now. Nothing goes live until you publish.</p>
  </Modal>
</template>
