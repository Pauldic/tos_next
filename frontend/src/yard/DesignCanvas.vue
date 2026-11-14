<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { distToSegment, drawOrder, hasFront, kindOf, minPoints, norm, pointsOf, polygonal, resizable, setPoints, sizeOf, toLocal, toSite, type Backdrop, type DBlock, type DItem } from './designerModel'

type Tool = 'select' | 'draw' | 'calibrate'
const props = defineProps<{
  items: DItem[]; blocks: DBlock[]; selected: string[]; snap: number; geometry: { slot: number; row: number }
  tool: Tool; drawClosed: boolean; drawMin: number; vertex: number
  backdrop: Backdrop | null; backdropHeight: number; backdropEdit: boolean
}>()
const emit = defineEmits<{
  select: [uids: string[]]
  commit: []
  drop: [payload: { kind: string; id: string }, x: number, z: number]
  drawn: [points: [number, number][]]
  calibrated: [a: [number, number], b: [number, number]]
  vertex: [index: number]
}>()

const el = ref<SVGSVGElement>()
const size = reactive({ w: 800, h: 600 })
const view = reactive({ s: 4, tx: 400, ty: 300 })
const cursor = ref<{ x: number; z: number } | null>(null)
const drawPts = ref<[number, number][]>([])
const calPts = ref<[number, number][]>([])
const marquee = ref<{ x0: number; z0: number; x1: number; z1: number } | null>(null)
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
const round = (v: number) => Math.round(v * 1000) / 1000
const px = (n: number) => n / view.s // pixels -> metres

function corners(it: DItem) {
  const { l, w } = sizeOf(it, props.blocks)
  return [[-l / 2, -w / 2], [l / 2, -w / 2], [l / 2, w / 2], [-l / 2, w / 2]].map(([a, b]) => toSite(it, a, b))
}
function fit() {
  let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity
  for (const it of props.items) {
    const pts = polygonal(it) ? pointsOf(it).map(([x, z]) => ({ x, z })) : corners(it)
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

// ---------- drawing a shape by points ----------
function finishDraw() {
  const pts: [number, number][] = []
  for (const p of drawPts.value) { const last = pts[pts.length - 1]; if (!last || Math.hypot(last[0] - p[0], last[1] - p[1]) > 0.05) pts.push(p) }
  drawPts.value = []
  if (pts.length >= props.drawMin) emit('drawn', pts)
  else if (pts.length) emit('drawn', [])
}
function cancelDraw() { drawPts.value = []; calPts.value = [] }
defineExpose({ fit, centre, zoomBy, finishDraw, cancelDraw })

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
    return ({ Asphalt: '#64748B', Concrete: '#CBD5E1', Gravel: '#A8A29E', Grass: '#86B97A', Sand: '#E7D8A8', Water: '#7DB6E0' } as Record<string, string>)[it.surface] || k?.colour
  }
  return k?.colour || '#CBD5E1'
}
const labelOf = (it: DItem) => (it.item_type === 'Block' ? `Block ${props.blocks.find((b) => b.name === it.yard_block)?.block_code || ''}` : it.label || kindOf(it.item_type)?.label || it.item_type)
const labelAt = (it: DItem) => {
  const p = pointsOf(it)
  if (!p.length) return { x: it.x || 0, z: it.z || 0 }
  return { x: p.reduce((n, q) => n + q[0], 0) / p.length, z: p.reduce((n, q) => n + q[1], 0) / p.length }
}
const ptsAttr = (pts: [number, number][]) => pts.map((p) => p.join(',')).join(' ')

function blockLines(it: DItem) {
  const b = props.blocks.find((x) => x.name === it.yard_block)
  if (!b) return ''
  const { l, w } = sizeOf(it, props.blocks)
  const d: string[] = []
  for (let i = 1; i < b.bay_count; i++) d.push(`M${-l / 2 + i * props.geometry.slot} ${-w / 2}V${w / 2}`)
  for (let r = 1; r < b.row_count; r++) d.push(`M${-l / 2} ${-w / 2 + r * props.geometry.row}H${l / 2}`)
  return d.join('')
}
function gate(it: DItem) {
  const { l, w } = sizeOf(it, props.blocks)
  const n = Math.max(1, Math.round(l / 4))
  const lane = l / n
  return {
    w, depth: Math.min(w, 12),
    xs: Array.from({ length: n - 1 }, (_, i) => -l / 2 + (i + 1) * lane),
    lanes: Array.from({ length: n }, (_, i) => -l / 2 + (i + 0.5) * lane),
  }
}

// ---------- gestures ----------
type Drag =
  | { kind: 'pan'; x: number; y: number; tx: number; ty: number; moved: boolean }
  | { kind: 'marquee'; x0: number; z0: number }
  | { kind: 'move'; start: { x: number; z: number }; orig: Map<string, { x: number; z: number; pts: [number, number][] }>; moved: boolean }
  | { kind: 'resize'; it: DItem; sx: number; sz: number }
  | { kind: 'rotate'; it: DItem }
  | { kind: 'vertex'; it: DItem; idx: number; moved: boolean }
  | { kind: 'backdrop'; start: { x: number; z: number }; ox: number; oz: number; moved: boolean }
let drag: Drag | null = null

function capture(ev: PointerEvent) { try { el.value!.setPointerCapture(ev.pointerId) } catch {} }

/** In draw and calibrate modes every click, wherever it lands, adds a point. Returns true when it handled the click. */
function toolClick(ev: PointerEvent) {
  if (props.tool === 'draw') {
    const w = world(ev)
    drawPts.value = [...drawPts.value, [snapTo(w.x), snapTo(w.z)]]
    return true
  }
  if (props.tool === 'calibrate') {
    const w = world(ev)
    calPts.value = [...calPts.value, [w.x, w.z]]
    if (calPts.value.length === 2) {
      const [a, b] = calPts.value
      calPts.value = []
      emit('calibrated', a, b)
    }
    return true
  }
  return false
}

function onBackgroundDown(ev: PointerEvent) {
  if (toolClick(ev)) return
  capture(ev)
  if (ev.shiftKey && ev.button === 0) {
    const w = world(ev)
    drag = { kind: 'marquee', x0: w.x, z0: w.z }
    marquee.value = { x0: w.x, z0: w.z, x1: w.x, z1: w.z }
    return
  }
  drag = { kind: 'pan', x: ev.clientX, y: ev.clientY, tx: view.tx, ty: view.ty, moved: false }
}
function onBackdropDown(ev: PointerEvent) {
  if (toolClick(ev)) return
  if (!props.backdropEdit || !props.backdrop) return onBackgroundDown(ev)
  capture(ev)
  drag = { kind: 'backdrop', start: world(ev), ox: props.backdrop.x, oz: props.backdrop.z, moved: false }
}
function onItemDown(ev: PointerEvent, it: DItem) {
  if (toolClick(ev)) return
  if (ev.button === 1) return onBackgroundDown(ev)
  capture(ev)
  let sel = props.selected
  if (ev.shiftKey) sel = sel.includes(it.uid) ? sel.filter((u) => u !== it.uid) : [...sel, it.uid]
  else if (!sel.includes(it.uid)) sel = [it.uid]
  emit('select', sel)
  emit('vertex', -1)
  const movable = props.items.filter((i) => sel.includes(i.uid) && !i.locked)
  if (!movable.length) { drag = null; return }
  drag = { kind: 'move', start: world(ev), orig: new Map(movable.map((i) => [i.uid, { x: i.x || 0, z: i.z || 0, pts: pointsOf(i) }])), moved: false }
}
function onHandleDown(ev: PointerEvent, kind: 'resize' | 'rotate', cx = 0, cz = 0) {
  const it = only.value
  if (!it || it.locked) return
  capture(ev)
  drag = kind === 'resize' ? { kind, it, sx: cx, sz: cz } : { kind, it }
}
function onVertexDown(ev: PointerEvent, idx: number) {
  const it = only.value
  if (!it || it.locked) return
  capture(ev)
  emit('vertex', idx)
  drag = { kind: 'vertex', it, idx, moved: false }
}
function onItemDouble(ev: MouseEvent, it: DItem) {
  if (props.tool === 'draw') return finishDraw()
  if (props.tool !== 'select' || it.locked) return
  const pts = pointsOf(it)
  if (!pts.length) return
  const w = world(ev)
  const closed = it.shape === 'Polygon'
  const n = pts.length
  let best = -1, bd = px(10)
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const d = distToSegment(w.x, w.z, pts[i], pts[(i + 1) % n])
    if (d < bd) { bd = d; best = i }
  }
  if (best < 0) return
  pts.splice(best + 1, 0, [round(snapTo(w.x)), round(snapTo(w.z))])
  setPoints(it, pts)
  emit('vertex', best + 1)
  emit('commit')
}

/** Moves the dragged item's edges onto the edges and centres of axis-aligned neighbours when they are within a few pixels. */
function edgeSnap(it: DItem, nx: number, nz: number) {
  if (props.snap <= 0 || polygonal(it) || Math.abs(Math.sin(((it.rotation || 0) * Math.PI) / 90)) > 1e-6) return { x: nx, z: nz }
  const half = (i: DItem) => {
    const { l, w } = sizeOf(i, props.blocks)
    const swap = Math.round((i.rotation || 0) / 90) % 2 !== 0
    return { hx: (swap ? w : l) / 2, hz: (swap ? l : w) / 2 }
  }
  const me = half(it)
  const tol = px(8)
  let bx = nx, bz = nz, dx = tol, dz = tol
  for (const o of props.items) {
    if (o.uid === it.uid || isSel(o) || polygonal(o) || Math.abs(Math.sin(((o.rotation || 0) * Math.PI) / 90)) > 1e-6) continue
    const h = half(o)
    for (const ex of [(o.x || 0) - h.hx, (o.x || 0) + h.hx, o.x || 0]) for (const mine of [-me.hx, me.hx, 0]) { const d = Math.abs(nx + mine - ex); if (d < dx) { dx = d; bx = ex - mine } }
    for (const ez of [(o.z || 0) - h.hz, (o.z || 0) + h.hz, o.z || 0]) for (const mine of [-me.hz, me.hz, 0]) { const d = Math.abs(nz + mine - ez); if (d < dz) { dz = d; bz = ez - mine } }
  }
  return { x: bx, z: bz }
}

function onMove(ev: PointerEvent) {
  if (props.tool !== 'select') cursor.value = world(ev)
  if (!drag) return
  if (drag.kind === 'pan') {
    const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true
    view.tx = drag.tx + dx
    view.ty = drag.ty + dy
    return
  }
  const p = world(ev)
  if (drag.kind === 'marquee') {
    marquee.value = { x0: drag.x0, z0: drag.z0, x1: p.x, z1: p.z }
  } else if (drag.kind === 'backdrop' && props.backdrop) {
    drag.moved = true
    props.backdrop.x = round(drag.ox + p.x - drag.start.x)
    props.backdrop.z = round(drag.oz + p.z - drag.start.z)
  } else if (drag.kind === 'move') {
    let dx = p.x - drag.start.x, dz = p.z - drag.start.z
    if (!drag.moved && Math.hypot(dx, dz) * view.s < 3) return
    drag.moved = true
    const entries = [...drag.orig.entries()]
    const [firstId, first] = entries[0]
    if (props.snap > 0) { dx = snapTo(first.x + dx) - first.x; dz = snapTo(first.z + dz) - first.z }
    if (entries.length === 1) {
      const it = props.items.find((i) => i.uid === firstId)!
      const s = edgeSnap(it, first.x + dx, first.z + dz)
      dx = s.x - first.x; dz = s.z - first.z
    }
    for (const it of props.items) {
      const o = drag.orig.get(it.uid)
      if (!o) continue
      it.x = round(o.x + dx); it.z = round(o.z + dz)
      if (o.pts.length) setPoints(it, o.pts.map(([x, z]) => [x + dx, z + dz] as [number, number]))
    }
  } else if (drag.kind === 'vertex') {
    drag.moved = true
    const pts = pointsOf(drag.it)
    if (pts[drag.idx]) { pts[drag.idx] = [snapTo(p.x), snapTo(p.z)]; setPoints(drag.it, pts) }
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
  if (d.kind === 'pan') { if (!d.moved && !ev.shiftKey) { emit('select', []); emit('vertex', -1) } return }
  if (d.kind === 'marquee') {
    const m = marquee.value
    marquee.value = null
    if (!m) return
    const x0 = Math.min(m.x0, m.x1), x1 = Math.max(m.x0, m.x1), z0 = Math.min(m.z0, m.z1), z1 = Math.max(m.z0, m.z1)
    if (x1 - x0 < px(4) && z1 - z0 < px(4)) return
    const hits = props.items.filter((it) => { const c = labelAt(it); return c.x >= x0 && c.x <= x1 && c.z >= z0 && c.z <= z1 }).map((i) => i.uid)
    emit('select', hits)
    return
  }
  if ((d.kind === 'move' || d.kind === 'vertex' || d.kind === 'backdrop') && !d.moved) return
  emit('commit')
}

// ---------- palette drops ----------
function onDragOver(ev: DragEvent) { if (ev.dataTransfer?.types.includes('application/x-tos')) { ev.preventDefault(); ev.dataTransfer.dropEffect = 'copy' } }
function onDrop(ev: DragEvent) {
  const raw = ev.dataTransfer?.getData('application/x-tos')
  if (!raw) return
  ev.preventDefault()
  const w = world(ev)
  emit('drop', JSON.parse(raw), snapTo(w.x), snapTo(w.z))
}
function onDouble() { if (props.tool === 'draw') finishDraw() }

// ---------- selection furniture ----------
const handles = computed(() => {
  const it = only.value
  if (!it || props.tool !== 'select') return null
  const { l, w } = sizeOf(it, props.blocks)
  return { it, l, w, can: resizable(it.item_type) && !polygonal(it) && !it.locked, rot: !it.locked && !polygonal(it) }
})
const hs = computed(() => px(9))
const verts = computed(() => (only.value && props.tool === 'select' ? pointsOf(only.value) : []))
const rubber = computed(() => (props.tool === 'draw' && drawPts.value.length && cursor.value ? [...drawPts.value, [cursor.value.x, cursor.value.z] as [number, number]] : drawPts.value))
const cursorStyle = computed(() => (props.tool === 'select' ? 'default' : 'crosshair'))
void minPoints
</script>

<template>
  <svg
    ref="el" class="h-full w-full touch-none select-none bg-surface-gray-2" :style="{ cursor: cursorStyle }"
    @pointerdown.self="onBackgroundDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp" @wheel.prevent="onWheel"
    @dragover="onDragOver" @drop="onDrop" @dblclick="onDouble" @pointerleave="cursor = null"
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
      <!-- the picture being traced -->
      <image
        v-if="backdrop && backdrop.image && backdrop.width > 0" :href="backdrop.image" preserveAspectRatio="none"
        :x="-backdrop.width / 2" :y="-backdropHeight / 2" :width="backdrop.width" :height="backdropHeight" :opacity="backdrop.opacity / 100"
        :transform="`translate(${backdrop.x} ${backdrop.z}) rotate(${backdrop.rotation})`"
        :style="{ pointerEvents: backdropEdit || tool === 'calibrate' ? 'auto' : 'none', cursor: backdropEdit ? 'move' : 'inherit' }"
        @pointerdown.stop="onBackdropDown"
      />

      <g v-for="it in ordered" :key="it.uid" :style="{ cursor: tool !== 'select' ? 'crosshair' : it.locked ? 'not-allowed' : 'move' }" @pointerdown.stop="onItemDown($event, it)" @dblclick.stop="onItemDouble($event, it)">
        <!-- shapes made of points -->
        <template v-if="pointsOf(it).length">
          <polygon v-if="it.shape === 'Polygon'" :points="ptsAttr(pointsOf(it))" :fill="fillOf(it)" fill-opacity="0.75" stroke="#334155" stroke-width="1" vector-effect="non-scaling-stroke" />
          <template v-else>
            <polyline :points="ptsAttr(pointsOf(it))" fill="none" :stroke="fillOf(it)" :stroke-width="it.item_type === 'Road' ? it.width || 12 : Math.max(0.4, px(3))" stroke-linejoin="round" stroke-opacity="0.85" />
            <polyline :points="ptsAttr(pointsOf(it))" fill="none" stroke="transparent" :stroke-width="Math.max(px(14), it.item_type === 'Road' ? it.width || 12 : 0)" stroke-linejoin="round" />
          </template>
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
            <line
              v-if="it.item_type === 'Block'" :x1="it.door_side === 'Higher bay end' ? sizeOf(it, blocks).l / 2 : -sizeOf(it, blocks).l / 2" :x2="it.door_side === 'Higher bay end' ? sizeOf(it, blocks).l / 2 : -sizeOf(it, blocks).l / 2"
              :y1="-sizeOf(it, blocks).w / 2" :y2="sizeOf(it, blocks).w / 2" stroke="#D97706" :stroke-width="px(4)"
            />
            <template v-if="it.item_type === 'Building' && hasFront(it.item_type)">
              <line :x1="-Math.min(3, sizeOf(it, blocks).l / 3) / 2" :x2="Math.min(3, sizeOf(it, blocks).l / 3) / 2" :y1="sizeOf(it, blocks).w / 2" :y2="sizeOf(it, blocks).w / 2" stroke="#DC2626" :stroke-width="px(5)" />
              <path :d="`M0 ${sizeOf(it, blocks).w / 2 + px(16)} L${px(7)} ${sizeOf(it, blocks).w / 2 + px(5)} L${-px(7)} ${sizeOf(it, blocks).w / 2 + px(5)} Z`" fill="#DC2626" />
            </template>
            <template v-if="it.item_type === 'Gate'">
              <rect v-for="x in gate(it).xs" :key="'b' + x" :x="x - 0.8" :y="-gate(it).depth / 2" width="1.6" :height="gate(it).depth" fill="#F1F5F9" stroke="#334155" stroke-width="1" vector-effect="non-scaling-stroke" />
              <path v-for="x in gate(it).lanes" :key="'a' + x" :d="`M${x} ${-gate(it).depth / 2 - px(2)}V${gate(it).w / 2 - px(12)}M${x - px(6)} ${gate(it).w / 2 - px(18)}L${x} ${gate(it).w / 2 - px(8)}L${x + px(6)} ${gate(it).w / 2 - px(18)}`" stroke="#F8FAFC" :stroke-width="px(2)" fill="none" />
            </template>
            <path v-if="it.item_type === 'Road' && it.direction && it.direction !== 'Two-way'" :d="it.direction === 'One-way reverse' ? `M${sizeOf(it, blocks).l / 4} 0H${-sizeOf(it, blocks).l / 4}M${-sizeOf(it, blocks).l / 4 + px(8)} ${-px(6)}L${-sizeOf(it, blocks).l / 4} 0L${-sizeOf(it, blocks).l / 4 + px(8)} ${px(6)}` : `M${-sizeOf(it, blocks).l / 4} 0H${sizeOf(it, blocks).l / 4}M${sizeOf(it, blocks).l / 4 - px(8)} ${-px(6)}L${sizeOf(it, blocks).l / 4} 0L${sizeOf(it, blocks).l / 4 - px(8)} ${px(6)}`" stroke="#F8FAFC" :stroke-width="px(2)" fill="none" />
          </template>
        </g>
      </g>

      <!-- names, kept upright -->
      <g style="pointer-events: none">
        <text
          v-for="it in ordered" :key="'t' + it.uid" :x="labelAt(it).x" :y="labelAt(it).z"
          text-anchor="middle" dominant-baseline="middle" :font-size="px(12)" fill="#0F172A" paint-order="stroke" stroke="#F8FAFC" :stroke-width="px(3)" stroke-opacity="0.8"
        >{{ it.item_type === 'Tree' || it.item_type === 'Light Mast' ? '' : labelOf(it) }}</text>
      </g>

      <!-- selection -->
      <template v-for="it in items.filter(isSel)" :key="'s' + it.uid">
        <g v-if="!polygonal(it)" :transform="`translate(${it.x || 0} ${it.z || 0}) rotate(${it.rotation || 0})`" style="pointer-events: none">
          <rect :x="-sizeOf(it, blocks).l / 2 - px(2)" :y="-sizeOf(it, blocks).w / 2 - px(2)" :width="sizeOf(it, blocks).l + px(4)" :height="sizeOf(it, blocks).w + px(4)" fill="none" stroke="#2563EB" stroke-width="2" stroke-dasharray="6 3" vector-effect="non-scaling-stroke" />
        </g>
        <g v-else style="pointer-events: none">
          <polygon v-if="it.shape === 'Polygon'" :points="ptsAttr(pointsOf(it))" fill="none" stroke="#2563EB" stroke-width="2" stroke-dasharray="6 3" vector-effect="non-scaling-stroke" />
          <polyline v-else :points="ptsAttr(pointsOf(it))" fill="none" stroke="#2563EB" stroke-width="2" stroke-dasharray="6 3" vector-effect="non-scaling-stroke" />
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
      <!-- points of a selected shape -->
      <circle
        v-for="(v, i) in verts" :key="'v' + i" :cx="v[0]" :cy="v[1]" :r="px(i === vertex ? 7 : 5.5)" :fill="i === vertex ? '#2563EB' : '#fff'" stroke="#2563EB" stroke-width="2" vector-effect="non-scaling-stroke"
        style="cursor: move" @pointerdown.stop="onVertexDown($event, i)"
      />

      <!-- a shape being drawn -->
      <g v-if="tool === 'draw'" style="pointer-events: none">
        <polygon v-if="drawClosed && rubber.length > 2" :points="ptsAttr(rubber)" fill="#2563EB" fill-opacity="0.15" stroke="#2563EB" stroke-width="2" vector-effect="non-scaling-stroke" />
        <polyline v-else :points="ptsAttr(rubber)" fill="none" stroke="#2563EB" stroke-width="2" vector-effect="non-scaling-stroke" />
        <circle v-for="(v, i) in drawPts" :key="'d' + i" :cx="v[0]" :cy="v[1]" :r="px(5)" fill="#2563EB" stroke="#fff" stroke-width="1.5" vector-effect="non-scaling-stroke" />
      </g>
      <!-- scale calibration marks -->
      <g v-if="tool === 'calibrate'" style="pointer-events: none">
        <circle v-for="(v, i) in calPts" :key="'c' + i" :cx="v[0]" :cy="v[1]" :r="px(7)" fill="#DC2626" stroke="#fff" stroke-width="2" vector-effect="non-scaling-stroke" />
      </g>
      <rect v-if="marquee" :x="Math.min(marquee.x0, marquee.x1)" :y="Math.min(marquee.z0, marquee.z1)" :width="Math.abs(marquee.x1 - marquee.x0)" :height="Math.abs(marquee.z1 - marquee.z0)" fill="#2563EB" fill-opacity="0.1" stroke="#2563EB" stroke-dasharray="4 3" stroke-width="1" vector-effect="non-scaling-stroke" style="pointer-events: none" />
    </g>
  </svg>
</template>
