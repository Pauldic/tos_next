import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

// Real ISO container dimensions in metres. The model is built once per length and shared by every instance.
export const REAL = { w: 2.438, h: 2.591, l20: 6.058, l40: 12.192 }

type RGB = [number, number, number]
const BODY: RGB = [1, 1, 1] // takes the shipping line colour
const STEEL: RGB = [0.66, 0.68, 0.7] // locking rods, hinges, brackets: galvanised steel
const CASTING: RGB = [0.28, 0.29, 0.31]
const DARK: RGB = [0.14, 0.15, 0.17]

/** Gives a part flat colour data. `tint` 1 = takes the line colour, 0 = keeps its own steel colour. */
function finish(g: THREE.BufferGeometry, rgb: RGB, tint: number): THREE.BufferGeometry {
  const n = g.index ? g.toNonIndexed() : g
  if (n.getAttribute('uv')) n.deleteAttribute('uv')
  if (!n.getAttribute('normal')) n.computeVertexNormals()
  const count = n.getAttribute('position').count
  const col = new Float32Array(count * 3)
  const t = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    col[i * 3] = rgb[0]; col[i * 3 + 1] = rgb[1]; col[i * 3 + 2] = rgb[2]
    t[i] = tint
  }
  n.setAttribute('color', new THREE.Float32BufferAttribute(col, 3))
  n.setAttribute('aTint', new THREE.Float32BufferAttribute(t, 1))
  return n
}

function box(w: number, h: number, d: number, x: number, y: number, z: number, rgb: RGB, tint: number) {
  const g = new THREE.BoxGeometry(w, h, d)
  g.translate(x, y, z)
  return finish(g, rgb, tint)
}

function rod(r: number, h: number, x: number, y: number, z: number, rgb: RGB) {
  const g = new THREE.CylinderGeometry(r, r, h, 8, 1)
  g.translate(x, y, z)
  return finish(g, rgb, 0)
}

/**
 * A corrugated panel. It runs along `axis` from a0 to a1 and from y0 to y1, and bulges outward from `fixed`
 * in the direction `sign` (+1 or -1) by `depth`. Every rib is real geometry, so the light catches it.
 */
function wall(axis: 'x' | 'z', a0: number, a1: number, y0: number, y1: number, fixed: number, sign: 1 | -1, rgb: RGB, tint: number, pitch = 0.2, depth = 0.036) {
  const periods = Math.max(1, Math.round((a1 - a0) / pitch))
  const step = (a1 - a0) / periods
  const prof: [number, number][] = [[0, 0], [0.3, 0], [0.5, 1], [0.8, 1]]
  const pts: [number, number][] = []
  for (let k = 0; k < periods; k++) for (const [u, d] of prof) pts.push([a0 + (k + u) * step, d * depth])
  pts.push([a1, 0])
  const flip = axis === 'x' ? sign < 0 : sign > 0
  const pos: number[] = []
  const P = (a: number, off: number, y: number) => (axis === 'x' ? [a, y, fixed + sign * off] : [fixed + sign * off, y, a])
  for (let i = 0; i < pts.length - 1; i++) {
    const A = P(pts[i][0], pts[i][1], y0)
    const B = P(pts[i + 1][0], pts[i + 1][1], y0)
    const C = P(pts[i + 1][0], pts[i + 1][1], y1)
    const D = P(pts[i][0], pts[i][1], y1)
    const tris = flip ? [A, C, B, A, D, C] : [A, B, C, A, C, D]
    for (const v of tris) pos.push(v[0], v[1], v[2])
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  g.computeVertexNormals()
  return finish(g, rgb, tint)
}

/** One container, centred on the origin, length along x. The doors are at the +x end. */
export function buildContainerGeometry(L: number): THREE.BufferGeometry {
  const { w: W, h: H } = REAL
  const hl = L / 2, hw = W / 2, hh = H / 2
  const rail = 0.12
  const y0 = -hh + rail, y1 = hh - rail
  const parts: THREE.BufferGeometry[] = []

  // long sides: vertical ribs between the top and bottom rails
  parts.push(wall('x', -hl + 0.12, hl - 0.12, y0, y1, hw - 0.056, 1, BODY, 1))
  parts.push(wall('x', -hl + 0.12, hl - 0.12, y0, y1, -(hw - 0.056), -1, BODY, 1))
  // roof, floor, rails, posts, corner castings
  parts.push(box(L - 0.02, 0.05, W - 0.1, 0, hh - 0.025, 0, BODY, 1))
  parts.push(box(L, 0.12, W - 0.2, 0, -hh + 0.06, 0, DARK, 0))
  for (const s of [1, -1]) {
    parts.push(box(L, rail, rail, 0, hh - rail / 2, s * (hw - rail / 2), BODY, 1))
    parts.push(box(L, rail, rail, 0, -hh + rail / 2, s * (hw - rail / 2), BODY, 1))
  }
  for (const sx of [1, -1]) for (const sz of [1, -1]) {
    parts.push(box(0.12, H - 0.2, 0.12, sx * (hl - 0.06), 0, sz * (hw - 0.06), BODY, 1))
    for (const sy of [1, -1]) parts.push(box(0.18, 0.16, 0.18, sx * (hl - 0.09), sy * (hh - 0.08), sz * (hw - 0.09), CASTING, 0))
  }

  // front end (closed wall) at -x
  parts.push(wall('z', -hw + rail, hw - rail, y0, y1, -hl + 0.056, -1, BODY, 1))

  // door end at +x: header, sill, two door leaves, the seam between them
  parts.push(box(0.14, 0.14, W - 0.24, hl - 0.07, hh - 0.07, 0, BODY, 1))
  parts.push(box(0.14, 0.14, W - 0.24, hl - 0.07, -hh + 0.07, 0, BODY, 1))
  const dy0 = -hh + 0.14, dy1 = hh - 0.14
  parts.push(wall('z', -hw + rail, -0.006, dy0, dy1, hl - 0.056, 1, BODY, 1))
  parts.push(wall('z', 0.006, hw - rail, dy0, dy1, hl - 0.056, 1, BODY, 1))
  parts.push(box(0.03, dy1 - dy0, 0.012, hl - 0.04, 0, 0, DARK, 0))

  // the two locking rods on each door leaf, with brackets and a handle on each
  const leafW = hw - rail - 0.006
  for (const side of [-1, 1]) {
    for (const f of [0.2, 0.8]) {
      const z = side * (0.006 + leafW * f)
      const rodH = H - 0.34
      parts.push(rod(0.022, rodH, hl + 0.02, 0, z, STEEL))
      for (const y of [-(hh - 0.22), 0, hh - 0.22]) parts.push(box(0.05, 0.06, 0.08, hl + 0.005, y, z, STEEL, 0))
      parts.push(box(0.04, 0.04, 0.3, hl + 0.06, -0.25, z - Math.sign(z) * 0.14, STEEL, 0)) // handle
      parts.push(box(0.06, 0.07, 0.1, hl + 0.045, hh - 0.17, z, DARK, 0)) // top cam keeper
      parts.push(box(0.06, 0.07, 0.1, hl + 0.045, -(hh - 0.17), z, DARK, 0)) // bottom cam keeper
    }
    for (const y of [-0.85, 0, 0.85]) parts.push(rod(0.025, 0.14, hl + 0.01, y, side * (hw - 0.1), STEEL)) // hinges
  }
  const merged = mergeGeometries(parts, false)!
  parts.forEach((p) => p.dispose())
  merged.computeBoundingSphere()
  return merged
}

/** Body material: vertex colours for steel parts, the instance colour (line colour) only where aTint is 1. */
export function buildContainerMaterial() {
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.52, metalness: 0.32 })
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float aTint;')
      .replace('vColor.xyz *= instanceColor.xyz;', 'vColor.xyz *= mix(vec3(1.0), instanceColor.xyz, aTint);')
  }
  return mat
}

/** "COSU5791184" -> "COSU 579118 4", the way owners print it. Anything else is shown as it is. */
export function isoGroups(no: string) {
  const m = /^([A-Z]{3}[UJZ])(\d{6})(\d)$/.exec(no)
  return m ? `${m[1]} ${m[2]} ${m[3]}` : no
}

/**
 * One big canvas holding the name tiles of the containers close to the camera. Each tile says the line name in
 * large letters and the container number below it. Tiles are reused as the camera moves.
 */
export class LabelAtlas {
  readonly texture: THREE.CanvasTexture
  readonly capacity: number
  private cv = document.createElement('canvas')
  private ctx: CanvasRenderingContext2D
  private cols = 8
  private rows = 16
  private tw = 512
  private th = 128
  private slots = new Map<string, { slot: number; key: string; used: number }>()
  private free: number[] = []
  private frame = 0
  dirty = false

  constructor() {
    this.capacity = this.cols * this.rows
    this.cv.width = this.cols * this.tw
    this.cv.height = this.rows * this.th
    this.ctx = this.cv.getContext('2d')!
    for (let i = this.capacity - 1; i >= 0; i--) this.free.push(i)
    this.texture = new THREE.CanvasTexture(this.cv)
    this.texture.colorSpace = THREE.SRGBColorSpace
    this.texture.generateMipmaps = false
    this.texture.minFilter = THREE.LinearFilter
    this.texture.magFilter = THREE.LinearFilter
    this.texture.anisotropy = 4
  }

  beginFrame() { this.frame++ }

  /** The tile for a container, drawn if it is new or its text colour changed. Returns its slot. */
  ensure(name: string, line: string, ink: string): number {
    const key = `${line}|${ink}`
    let e = this.slots.get(name)
    if (!e) {
      let slot = this.free.pop()
      if (slot === undefined) {
        let oldest: [string, { slot: number; key: string; used: number }] | null = null
        for (const kv of this.slots) if (kv[1].used < this.frame && (!oldest || kv[1].used < oldest[1].used)) oldest = kv
        if (!oldest) return -1
        slot = oldest[1].slot
        this.slots.delete(oldest[0])
      }
      e = { slot, key: '', used: this.frame }
      this.slots.set(name, e)
    }
    e.used = this.frame
    if (e.key !== key) {
      e.key = key
      this.draw(e.slot, name, line, ink)
    }
    return e.slot
  }

  /** u0, v0, du, dv of a tile in texture space */
  uv(slot: number) {
    const col = slot % this.cols
    const row = Math.floor(slot / this.cols)
    return { u0: (col * this.tw) / this.cv.width, v0: 1 - ((row + 1) * this.th) / this.cv.height, du: this.tw / this.cv.width, dv: this.th / this.cv.height }
  }

  private draw(slot: number, name: string, line: string, ink: string) {
    const x = (slot % this.cols) * this.tw
    const y = Math.floor(slot / this.cols) * this.th
    const g = this.ctx
    g.clearRect(x, y, this.tw, this.th)
    g.fillStyle = ink
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    const fit = (text: string, weight: string, size: number, max: number) => {
      let s = size
      do {
        g.font = `${weight} ${s}px Arial, Helvetica, sans-serif`
        if (g.measureText(text).width <= max) break
        s -= 4
      } while (s > 24)
    }
    const number = isoGroups(name)
    if (line) {
      fit(line.toUpperCase(), '800', 76, this.tw - 28)
      g.fillText(line.toUpperCase(), x + this.tw / 2, y + 40)
      fit(number, '700', 50, this.tw - 28)
      g.fillText(number, x + this.tw / 2, y + 98)
    } else {
      fit(number, '700', 64, this.tw - 28)
      g.fillText(number, x + this.tw / 2, y + this.th / 2)
    }
    this.dirty = true
  }

  flush() {
    if (this.dirty) { this.texture.needsUpdate = true; this.dirty = false }
  }

  dispose() { this.texture.dispose() }
}
