<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { drawOrder, hasFront, kindOf, norm, resizable, sizeOf, toLocal, toSite, type DBlock, type DItem } from './designerModel'
import { parsePoints } from './layoutRender'

const props = defineProps<{ items: DItem[]; blocks: DBlock[]; selected: string[]; snap: number; geometry: { slot: number; row: number } }>()
const emit = defineEmits<{
  select: [uids: string[]]
  commit: []
  drop: [payload: { kind: string; id: string }, x: number, z: number]
}>()

const el = ref<SVGSVGElement>()
const size = reactive({ w: 800, h: 600 })
const view = reactive({ s: 4, tx: 400, ty: 300 })
let ro: ResizeObserver | null = null

onMounted(() => {
  ro = new ResizeObserver(() => {
    const r = el.value!.getBoundingClientRect()
    const first = size.w === 800 && size.h === 600
    size.w = r.width || 800
    size.h = r.height || 600
    if (first) fit()
  })
  ro.observe(el.value!)
})
onBeforeUnmount(() => ro?.disconnect())

// ---------- coordinates ----------
const sx = (x: number) => view.tx + x * view.s
const sz = (z: number) => view.ty + z * view.s
function world(ev: { clientX: number; clientY: number }) {
  const r = el.value!.getBoundingClientRect()
  return { x: (ev.clientX - r.left - view.tx) / view.s, z: (ev.clientY - r.top - view.ty) / view.s }
}
const snapTo = (v: number) => (props.snap > 0 ? Math.round(v / props.snap) * props.snap : v)

function corners(it: DItem) {
  const { l, w } = sizeOf(it, props.blocks)
  return [[-l / 2, -w / 2], [l / 2, -w / 2], [l / 2, w / 2], [-l / 2, w / 2]].map(([a, b]) => toSite(it, a, b))
}
function pointsOf(it: DItem) {
  return it.shape === 'Polygon' || it.shape === 'Polyline' ? parsePoints(it.points) : []
}

function fit() {
  let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity
  for (const it of props.items) {
    const pts = pointsOf(it).length ? pointsOf(it).map(([x, z]) => ({ x, z })) : corners(it)
    for (const p of pts) { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); z0 = Math.min(z0, p.z); z1 = Math.max(z1, p.z) }
  }
  if (!isFinite(x0)) { x0 = -50; x1 = 50; z0 = -50; z1 = 50 }
  const pad = 30
  const s = Math.min(size.w / (x1 - x0 + pad * 2), size.h / (z1 - z0 + pad * 2))
  view.s = Math.max(0.3, Math.min(30, s))
  view.tx = size.w / 2 - ((x0 + x1) / 2) * view.s
  view.ty = size.h / 2 - ((z0 + z1) / 2) * view.s
}
function centre() {
  return { x: (size.w / 2 - view.tx) / view.s, z: (size.h / 2 - view.ty) / view.s }
}
function zoomBy(f: number, cx = size.w / 2, cy = size.h / 2) {
  const s = Math.max(0.3, Math.min(40, view.s * f))
  const wx = (cx - view.tx) / view.s, wz = (cy - view.ty) / view.s
  view.s = s
  view.tx = cx - wx * s
  view.ty = cy - wz * s
}
function onWheel(ev: WheelEvent) {
  const r = el.value!.getBoundingClientRect()
  zoomBy(Math.pow(1.0015, -ev.deltaY), ev.clientX - r.left, ev.clientY - r.top)
}
defineExpose({ fit, centre, zoomBy })

// ---------- grid ----------
const gridStep = computed(() => (view.s >= 12 ? 1 : view.s >= 2.5 ? 10 : 100))
const gridMajor = computed(() => gridStep.value * 10)

// ---------- drawing helpers ----------
const ordered = computed(() => drawOrder(props.items))
const isSel = (it: DItem) => props.selected.includes(it.uid)
const only = computed(() => (props.selected.length === 1 ? props.items.find((i) => i.uid === props.selected[0]) || null : null))
const fillOf = (it: DItem) => {
  if (it.colour) return it.colour
  if (it.item_type === 'Block') return '#93C5FD'
  const k = kindOf(it.item_type)
  if (['Ground', 'Road', 'Car Park', 'Truck Park'].includes(it.item_type) && it.surface) {
    return { Asphalt: '#64748B', Concrete: '#CBD5E1', Gravel: '#A8A29E', Grass: '#86B97A', Sand: '#E7D8A8', Water: '#7DB6E0' }[it.surface] || k?.colour
  }
  return k?.colour || '#CBD5E1'
}
const labelOf = (it: DItem) => (it.item_type === 'Block' ? `Block ${props.blocks.find((b) => b.name === it.yard_block)?.block_code || ''}` : it.label || kindOf(it.item_type)?.label || it.item_type)
const px = (n: number) => n / view.s // pixels -> metres

function blockLines(it: DItem) {
  const b = props.blocks.find((x) => x.name === it.yard_block)
  if (!b) return ''
  const { l, w } = sizeOf(it, props.blocks)
  const d: string[] = []
  for (let i = 1; i < b.bay_count; i++) d.push(`M${-l / 2 + i * props.geometry.slot} ${-w / 2}V${w / 2}`)
  for (let r = 1; r < b.row_count; r++) d.push(`M${-l / 2} ${-w / 2 + r * props.geometry.row}H${l / 2}`)
  return d.join('')
}

// ---------- gestures ----------
type Drag =
  | { kind: 'pan'; x: number; y: number; tx: number; ty: number; moved: boolean }
  | { kind: 'move'; start: { x: number; z: number }; orig: Map<string, { x: number; z: number }>; moved: boolean }
  | { kind: 'resize'; it: DItem; sx: number; sz: number }
  | { kind: 'rotate'; it: DItem }
let drag: Drag | null = null

function capture(ev: PointerEvent) { try { el.value!.setPointerCapture(ev.pointerId) } catch {} }

function onBackgroundDown(ev: PointerEvent) {
  capture(ev)
  drag = { kind: 'pan', x: ev.clientX, y: ev.clientY, tx: view.tx, ty: view.ty, moved: false }
}
function onItemDown(ev: PointerEvent, it: DItem) {
  if (ev.button === 1) return onBackgroundDown(ev)
  capture(ev)
  let sel = props.selected
  if (ev.shiftKey) sel = sel.includes(it.uid) ? sel.filter((u) => u !== it.uid) : [...sel, it.uid]
  else if (!sel.includes(it.uid)) sel = [it.uid]
  emit('select', sel)
  const movable = props.items.filter((i) => sel.includes(i.uid) && !i.locked && !pointsOf(i).length)
  if (!movable.length) { drag = null; return }
  drag = { kind: 'move', start: world(ev), orig: new Map(movable.map((i) => [i.uid, { x: i.x || 0, z: i.z || 0 }])), moved: false }
}
function onHandleDown(ev: PointerEvent, kind: 'resize' | 'rotate', cx = 0, cz = 0) {
  const it = only.value
  if (!it || it.locked) return
  capture(ev)
  drag = kind === 'resize' ? { kind, it, sx: cx, sz: cz } : { kind, it }
}

function onMove(ev: PointerEvent) {
  if (!drag) return
  if (drag.kind === 'pan') {
    const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true
    view.tx = drag.tx + dx
    view.ty = drag.ty + dy
    return
  }
  const p = world(ev)
  if (drag.kind === 'move') {
    let dx = p.x - drag.start.x, dz = p.z - drag.start.z
    if (!drag.moved && Math.hypot(dx, dz) * view.s < 3) return
    drag.moved = true
    const first = [...drag.orig.values()][0]
    if (props.snap > 0 && first) { dx = snapTo(first.x + dx) - first.x; dz = snapTo(first.z + dz) - first.z }
    for (const it of props.items) {
      const o = drag.orig.get(it.uid)
      if (o) { it.x = round(o.x + dx); it.z = round(o.z + dz) }
    }
  } else if (drag.kind === 'rotate') {
    const it = drag.it
    let deg = (Math.atan2(p.x - (it.x || 0), -(p.z - (it.z || 0))) * 180) / Math.PI
    if (props.snap > 0 && !ev.shiftKey) deg = Math.round(deg / 15) * 15
    it.rotation = norm(deg)
  } else if (drag.kind === 'resize') {
    const it = drag.it
    const { l, w } = sizeOf(it, props.blocks)
    const q = toLocal(it, p.x, p.z)
    const ax = -drag.sx * (l / 2), az = -drag.sz * (w / 2) // the corner that stays put
    const nl = Math.max(0.2, round(snapTo(Math.abs(q.x - ax))))
    const nw = Math.max(0.2, round(snapTo(Math.abs(q.z - az))))
    const dirx = Math.sign(q.x - ax) || drag.sx, dirz = Math.sign(q.z - az) || drag.sz
    const c = toSite(it, ax + (dirx * nl) / 2, az + (dirz * nw) / 2)
    it.length = nl; it.width = nw
    it.x = round(c.x); it.z = round(c.z)
  }
}
function onUp(ev: PointerEvent) {
  const d = drag
  drag = null
  try { el.value!.releasePointerCapture(ev.pointerId) } catch {}
  if (!d) return
  if (d.kind === 'pan') { if (!d.moved && !ev.shiftKey) emit('select', []); return }
  if (d.kind === 'move' && !d.moved) return
  emit('commit')
}
const round = (v: number) => Math.round(v * 1000) / 1000

// ---------- palette drops ----------
function onDragOver(ev: DragEvent) { if (ev.dataTransfer?.types.includes('application/x-tos')) { ev.preventDefault(); ev.dataTransfer.dropEffect = 'copy' } }
function onDrop(ev: DragEvent) {
  const raw = ev.dataTransfer?.getData('application/x-tos')
  if (!raw) return
  ev.preventDefault()
  const w = world(ev)
  emit('drop', JSON.parse(raw), snapTo(w.x), snapTo(w.z))
}

// ---------- selection furniture ----------
const handles = computed(() => {
  const it = only.value
  if (!it) return null
  const { l, w } = sizeOf(it, props.blocks)
  return { it, l, w, can: resizable(it.item_type) && !pointsOf(it).length && !it.locked, rot: !it.locked && !pointsOf(it).length }
})
const hs = computed(() => px(9))
</script>

<template>
  <svg
    ref="el" class="h-full w-full touch-none select-none bg-surface-gray-2" :style="{ cursor: 'default' }"
    @pointerdown.self="onBackgroundDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp" @wheel.prevent="onWheel"
    @dragover="onDragOver" @drop="onDrop"
  >
    <defs>
      <pattern id="g-minor" patternUnits="userSpaceOnUse" :x="view.tx" :y="view.ty" :width="gridStep * view.s" :height="gridStep * view.s">
        <path :d="`M${gridStep * view.s} 0H0V${gridStep * view.s}`" fill="none" stroke="currentColor" stroke-opacity="0.12" />
      </pattern>
      <pattern id="g-major" patternUnits="userSpaceOnUse" :x="view.tx" :y="view.ty" :width="gridMajor * view.s" :height="gridMajor * view.s">
        <path :d="`M${gridMajor * view.s} 0H0V${gridMajor * view.s}`" fill="none" stroke="currentColor" stroke-opacity="0.25" />
      </pattern>
    </defs>
    <g class="text-ink-gray-5" style="pointer-events: none">
      <rect width="100%" height="100%" fill="url(#g-minor)" />
      <rect width="100%" height="100%" fill="url(#g-major)" />
      <line :x1="sx(0)" :x2="sx(0)" y1="0" y2="100%" stroke="currentColor" stroke-opacity="0.35" />
      <line x1="0" x2="100%" :y1="sz(0)" :y2="sz(0)" stroke="currentColor" stroke-opacity="0.35" />
    </g>

    <g :transform="`translate(${view.tx} ${view.ty}) scale(${view.s})`">
      <g v-for="it in ordered" :key="it.uid" :style="{ cursor: it.locked ? 'not-allowed' : 'move' }" @pointerdown.stop="onItemDown($event, it)">
        <!-- polygons and polylines made in the Desk -->
        <template v-if="pointsOf(it).length">
          <polygon v-if="it.shape === 'Polygon'" :points="pointsOf(it).map((p) => p.join(',')).join(' ')" :fill="fillOf(it)" fill-opacity="0.75" stroke="#334155" stroke-width="1" vector-effect="non-scaling-stroke" />
          <polyline v-else :points="pointsOf(it).map((p) => p.join(',')).join(' ')" fill="none" :stroke="fillOf(it)" :stroke-width="it.item_type === 'Road' ? it.width || 12 : 0.5" stroke-linejoin="round" />
        </template>
        <g v-else :transform="`translate(${it.x || 0} ${it.z || 0}) rotate(${it.rotation || 0})`">
          <template v-if="it.item_type === 'Tree'">
            <circle r="2.5" :fill="fillOf(it)" fill-opacity="0.85" stroke="#334155" stroke-width="1" vector-effect="non-scaling-stroke" />
          </template>
          <template v-else-if="it.item_type === 'Light Mast'">
            <circle :r="Math.max(1, px(5))" :fill="fillOf(it)" stroke="#334155" stroke-width="1" vector-effect="non-scaling-stroke" />
          </template>
          <template v-else>
            <rect
              :x="-sizeOf(it, blocks).l / 2" :y="-sizeOf(it, blocks).w / 2" :width="sizeOf(it, blocks).l" :height="sizeOf(it, blocks).w"
              :fill="fillOf(it)" :fill-opacity="it.item_type === 'Block' ? 0.55 : 0.8" stroke="#334155" stroke-width="1" vector-effect="non-scaling-stroke"
            />
            <path v-if="it.item_type === 'Block'" :d="blockLines(it)" stroke="#1E3A8A" stroke-opacity="0.35" stroke-width="0.5" vector-effect="non-scaling-stroke" fill="none" />
            <!-- block doors -->
            <line
              v-if="it.item_type === 'Block'" :x1="it.door_side === 'Higher bay end' ? sizeOf(it, blocks).l / 2 : -sizeOf(it, blocks).l / 2" :x2="it.door_side === 'Higher bay end' ? sizeOf(it, blocks).l / 2 : -sizeOf(it, blocks).l / 2"
              :y1="-sizeOf(it, blocks).w / 2" :y2="sizeOf(it, blocks).w / 2" stroke="#D97706" :stroke-width="px(4)"
            />
            <!-- building entrance -->
            <template v-if="hasFront(it.item_type)">
              <line :x1="-Math.min(3, sizeOf(it, blocks).l / 3) / 2" :x2="Math.min(3, sizeOf(it, blocks).l / 3) / 2" :y1="sizeOf(it, blocks).w / 2" :y2="sizeOf(it, blocks).w / 2" stroke="#DC2626" :stroke-width="px(5)" />
              <path :d="`M0 ${sizeOf(it, blocks).w / 2 + px(16)} L${px(7)} ${sizeOf(it, blocks).w / 2 + px(5)} L${-px(7)} ${sizeOf(it, blocks).w / 2 + px(5)} Z`" fill="#DC2626" />
            </template>
            <!-- road direction -->
            <path v-if="it.item_type === 'Road' && it.direction && it.direction !== 'Two-way'" :d="it.direction === 'One-way reverse' ? `M${sizeOf(it, blocks).l / 4} 0H${-sizeOf(it, blocks).l / 4}M${-sizeOf(it, blocks).l / 4 + px(8)} ${-px(6)}L${-sizeOf(it, blocks).l / 4} 0L${-sizeOf(it, blocks).l / 4 + px(8)} ${px(6)}` : `M${-sizeOf(it, blocks).l / 4} 0H${sizeOf(it, blocks).l / 4}M${sizeOf(it, blocks).l / 4 - px(8)} ${-px(6)}L${sizeOf(it, blocks).l / 4} 0L${sizeOf(it, blocks).l / 4 - px(8)} ${px(6)}`" stroke="#F8FAFC" :stroke-width="px(2)" fill="none" />
          </template>
        </g>
      </g>

      <!-- names, kept upright -->
      <g style="pointer-events: none">
        <text
          v-for="it in ordered" :key="'t' + it.uid" :x="pointsOf(it).length ? pointsOf(it)[0][0] : it.x || 0" :y="pointsOf(it).length ? pointsOf(it)[0][1] : it.z || 0"
          text-anchor="middle" dominant-baseline="middle" :font-size="px(12)" fill="#0F172A" paint-order="stroke" stroke="#F8FAFC" :stroke-width="px(3)" stroke-opacity="0.8"
        >{{ it.item_type === 'Tree' || it.item_type === 'Light Mast' ? '' : labelOf(it) }}</text>
      </g>

      <!-- selection -->
      <template v-for="it in items.filter(isSel)" :key="'s' + it.uid">
        <g v-if="!pointsOf(it).length" :transform="`translate(${it.x || 0} ${it.z || 0}) rotate(${it.rotation || 0})`" style="pointer-events: none">
          <rect :x="-sizeOf(it, blocks).l / 2 - px(2)" :y="-sizeOf(it, blocks).w / 2 - px(2)" :width="sizeOf(it, blocks).l + px(4)" :height="sizeOf(it, blocks).w + px(4)" fill="none" stroke="#2563EB" stroke-width="2" stroke-dasharray="6 3" vector-effect="non-scaling-stroke" />
        </g>
      </template>
      <g v-if="handles" :transform="`translate(${handles.it.x || 0} ${handles.it.z || 0}) rotate(${handles.it.rotation || 0})`">
        <template v-if="handles.can">
          <rect
            v-for="c in [[-1, -1], [1, -1], [1, 1], [-1, 1]]" :key="c.join()" :x="(c[0] * handles.l) / 2 - hs / 2" :y="(c[1] * handles.w) / 2 - hs / 2" :width="hs" :height="hs"
            fill="#fff" stroke="#2563EB" stroke-width="2" vector-effect="non-scaling-stroke" style="cursor: nwse-resize" @pointerdown.stop="onHandleDown($event, 'resize', c[0], c[1])"
          />
        </template>
        <template v-if="handles.rot">
          <line x1="0" :y1="-handles.w / 2" x2="0" :y2="-handles.w / 2 - px(26)" stroke="#2563EB" stroke-width="1.5" vector-effect="non-scaling-stroke" style="pointer-events: none" />
          <circle cx="0" :cy="-handles.w / 2 - px(26)" :r="px(7)" fill="#2563EB" stroke="#fff" stroke-width="2" vector-effect="non-scaling-stroke" style="cursor: grab" @pointerdown.stop="onHandleDown($event, 'rotate')" />
        </template>
      </g>
    </g>
  </svg>
</template>
