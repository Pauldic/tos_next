import type { LayoutItem } from './layoutRender'

// Shared by the yard designer's editor, inspector and preview.
export interface DItem extends LayoutItem {
  uid: string
  locked?: number | boolean
}
export interface DBlock { name: string; block_code: string; block_type?: string; bay_count: number; row_count: number; max_tier: number; w: number; d: number }

export interface Kind { type: string; label: string; icon: string; group: 'Yard' | 'Ground and roads' | 'Buildings and gates' | 'Equipment and scenery'; length: number; width: number; height: number; surface?: string; hint: string; colour: string }

// colours used for the flat 2D plan only; the 3D view has its own look
export const KINDS: Kind[] = [
  { type: 'Road', label: 'Road', icon: 'lucide-route', group: 'Ground and roads', length: 60, width: 12, height: 0, surface: 'Asphalt', hint: 'A road strip with a centre line. Set one-way to draw arrows.', colour: '#64748B' },
  { type: 'Ground', label: 'Paved area', icon: 'lucide-square', group: 'Ground and roads', length: 40, width: 40, height: 0, surface: 'Concrete', hint: 'Concrete, asphalt, gravel, grass, sand or water.', colour: '#CBD5E1' },
  { type: 'Car Park', label: 'Car park', icon: 'lucide-car', group: 'Ground and roads', length: 30, width: 15, height: 0, surface: 'Asphalt', hint: 'Painted car bays. Bay width is set in Settings.', colour: '#94A3B8' },
  { type: 'Truck Park', label: 'Truck park', icon: 'lucide-truck', group: 'Ground and roads', length: 48, width: 24, height: 0, surface: 'Asphalt', hint: 'Painted truck bays.', colour: '#94A3B8' },
  { type: 'Rail Track', label: 'Rail track', icon: 'lucide-train-track', group: 'Ground and roads', length: 100, width: 1.435, height: 0, hint: 'Width is the gauge between the rails.', colour: '#78716C' },
  { type: 'Building', label: 'Building', icon: 'lucide-building-2', group: 'Buildings and gates', length: 24, width: 16, height: 8, hint: 'Office, warehouse or workshop. The arrow shows the entrance.', colour: '#CBD5E1' },
  { type: 'Gate', label: 'Gate', icon: 'lucide-door-open', group: 'Buildings and gates', length: 12, width: 8, height: 4, hint: 'Gate booth with barriers.', colour: '#38BDF8' },
  { type: 'Weighbridge', label: 'Weighbridge', icon: 'lucide-scale', group: 'Buildings and gates', length: 18, width: 4, height: 0.5, hint: 'A truck scale.', colour: '#A1A1AA' },
  { type: 'Heap', label: 'Heap', icon: 'lucide-mountain', group: 'Yard', length: 20, width: 20, height: 4, hint: 'A pile of bulk cargo.', colour: '#B8A58A' },
  { type: 'Crane', label: 'Crane', icon: 'lucide-construction', group: 'Equipment and scenery', length: 12, width: 30, height: 30, hint: 'A portal crane.', colour: '#F59E0B' },
  { type: 'Fence', label: 'Fence', icon: 'lucide-fence', group: 'Equipment and scenery', length: 50, width: 0.4, height: 2.4, hint: 'A straight fence.', colour: '#64748B' },
  { type: 'Light Mast', label: 'Light mast', icon: 'lucide-lamp', group: 'Equipment and scenery', length: 1, width: 1, height: 25, hint: 'A tall floodlight.', colour: '#FBBF24' },
  { type: 'Tree', label: 'Tree', icon: 'lucide-tree-pine', group: 'Equipment and scenery', length: 5, width: 5, height: 7, hint: 'Scenery.', colour: '#4D8B45' },
  { type: 'Label', label: 'Text label', icon: 'lucide-type', group: 'Equipment and scenery', length: 16, width: 4, height: 0, hint: 'Text lying on the ground.', colour: '#475569' },
]
export const kindOf = (type: string) => KINDS.find((k) => k.type === type)

// back to front, so small things are never hidden under big ones
const ORDER = ['Ground', 'Road', 'Car Park', 'Truck Park', 'Rail Track', 'Heap', 'Block', 'Weighbridge', 'Gate', 'Building', 'Fence', 'Crane', 'Light Mast', 'Tree', 'Label']
export const drawOrder = (items: DItem[]) => [...items].sort((a, b) => ORDER.indexOf(a.item_type) - ORDER.indexOf(b.item_type))

export const SURFACES = ['Asphalt', 'Concrete', 'Gravel', 'Grass', 'Sand', 'Water']
export const BASE_SURFACES = ['Default', ...SURFACES]
export const hasFront = (t: string) => t === 'Building'
export const resizable = (t: string) => !['Block', 'Light Mast', 'Tree'].includes(t)

let counter = 0
export const uid = () => `i${Date.now().toString(36)}${(counter++).toString(36)}`

export function blockEnrich(it: DItem, blocks: DBlock[]): DItem | null {
  if (it.item_type !== 'Block') return it
  const b = blocks.find((x) => x.name === it.yard_block)
  if (!b) return null
  return { ...it, block_code: b.block_code, bay_count: b.bay_count, row_count: b.row_count, length: b.w, width: b.d }
}

/** Length and width an item has on the plan. */
export function sizeOf(it: DItem, blocks: DBlock[]) {
  if (it.item_type === 'Block') {
    const b = blocks.find((x) => x.name === it.yard_block)
    return { l: b?.w || 0, w: b?.d || 0 }
  }
  const k = kindOf(it.item_type)
  return { l: it.length || k?.length || 1, w: it.width || k?.width || 1 }
}

export const rad = (deg: number) => (deg * Math.PI) / 180
export const norm = (deg: number) => ((Math.round(deg * 100) / 100) % 360 + 360) % 360

/** Site point -> item-local point and back. */
export function toLocal(it: DItem, x: number, z: number) {
  const a = rad(it.rotation || 0), c = Math.cos(a), s = Math.sin(a)
  const dx = x - (it.x || 0), dz = z - (it.z || 0)
  return { x: dx * c + dz * s, z: -dx * s + dz * c }
}
export function toSite(it: DItem, lx: number, lz: number) {
  const a = rad(it.rotation || 0), c = Math.cos(a), s = Math.sin(a)
  return { x: (it.x || 0) + lx * c - lz * s, z: (it.z || 0) + lx * s + lz * c }
}
export function hit(it: DItem, blocks: DBlock[], x: number, z: number, pad = 0) {
  const { l, w } = sizeOf(it, blocks)
  const p = toLocal(it, x, z)
  return Math.abs(p.x) <= l / 2 + pad && Math.abs(p.z) <= w / 2 + pad
}

/** Which way the entrance of a building faces in site terms, for the compass buttons: rotation that points it at N, E, S or W. */
export const FACING: { label: string; rotation: number }[] = [
  { label: 'North', rotation: 180 },
  { label: 'East', rotation: 270 },
  { label: 'South', rotation: 0 },
  { label: 'West', rotation: 90 },
]
export function facingName(rotation: number) {
  const r = norm(rotation)
  const near = FACING.find((f) => Math.abs(((r - f.rotation + 540) % 360) - 180) < 1)
  return near?.label || ''
}

/** Items as stored on the server (no client-only keys). */
export function plain(it: DItem) {
  const { uid: _u, block_code: _a, bay_count: _b, row_count: _c, ...rest } = it as any
  return rest
}

export class History {
  private stack: string[] = []
  private at = -1
  constructor(private limit = 100) {}
  reset(state: string) { this.stack = [state]; this.at = 0 }
  push(state: string) {
    if (state === this.stack[this.at]) return false
    this.stack = this.stack.slice(0, this.at + 1)
    this.stack.push(state)
    if (this.stack.length > this.limit) this.stack.shift()
    this.at = this.stack.length - 1
    return true
  }
  get canUndo() { return this.at > 0 }
  get canRedo() { return this.at < this.stack.length - 1 }
  undo() { return this.canUndo ? this.stack[--this.at] : null }
  redo() { return this.canRedo ? this.stack[++this.at] : null }
}
