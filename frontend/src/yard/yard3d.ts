import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

// 1 unit = 1 metre. A slot is one 20 ft bay; a 40 ft container spans two neighbouring bays.
const SLOT = 6.4
const ROW = 3.2
const TIER_H = 2.7
const WIDTH = 2.44
const BLOCK_GAP = 16
const COLUMNS = 2
const PALETTE = ['#2563EB', '#0EA5E9', '#14B8A6', '#F97316', '#8B5CF6', '#EC4899', '#84CC16', '#EAB308']

export interface Snapshot {
  blocks: any[]
  stacks: any[]
  containers: any[]
  lines: any[]
}
export interface Filter {
  line?: string | null
  holdsOnly?: boolean
  cargo?: 'Full' | 'Empty' | null
}
interface Pos { x: number; y: number; z: number; len: number }

const THEMES = {
  light: { bg: '#EEF2F7', ground: '#E2E8F0', slab: '#F8FAFC', grid: '#CBD5E1', text: '#334155', faded: '#CBD5E1', hold: '#DC2626', flash: '#F59E0B', sun: 2.2, hemi: 1.1 },
  dark: { bg: '#0B1220', ground: '#0F172A', slab: '#1E293B', grid: '#334155', text: '#CBD5E1', faded: '#334155', hold: '#F87171', flash: '#FBBF24', sun: 1.6, hemi: 0.8 },
}

export class YardScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private ground = new THREE.Group()
  private mesh: THREE.InstancedMesh | null = null
  private capacity = 0
  private outline: THREE.LineSegments
  private sun: THREE.DirectionalLight
  private hemi: THREE.HemisphereLight
  private raf = 0
  private flashTimer: ReturnType<typeof setInterval> | null = null
  private ro: ResizeObserver
  private theme: 'light' | 'dark' = 'light'

  private snap: Snapshot = { blocks: [], stacks: [], containers: [], lines: [] }
  private filter: Filter = {}
  private layoutKey = ''
  private stackInfo = new Map<string, { block: string; bay: number; row: number }>()
  private origin = new Map<string, { x: number; z: number; w: number; d: number }>()
  private index: string[] = []
  private pos = new Map<string, Pos>()
  private prevKey = new Map<string, string>()
  private flashUntil = new Map<string, number>()
  private selected: string | null = null
  private fitted = false
  private raycaster = new THREE.Raycaster()
  private down: { x: number; y: number } | null = null
  private moving = false

  constructor(
    private el: HTMLElement,
    private cb: { onPick: (name: string | null) => void; onHover: (h: { name: string; x: number; y: number } | null) => void },
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    el.appendChild(this.renderer.domElement)
    this.renderer.domElement.style.display = 'block'
    this.renderer.domElement.style.touchAction = 'none'

    this.camera = new THREE.PerspectiveCamera(40, 1, 1, 3000)
    this.camera.position.set(120, 110, 160)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.maxPolarAngle = Math.PI / 2.05
    this.controls.minDistance = 8
    this.controls.maxDistance = 900
    this.controls.addEventListener('change', () => this.render())

    this.hemi = new THREE.HemisphereLight('#ffffff', '#94a3b8', 1)
    this.sun = new THREE.DirectionalLight('#ffffff', 2)
    this.sun.position.set(-120, 220, 90)
    this.sun.castShadow = true
    this.sun.shadow.mapSize.set(2048, 2048)
    this.scene.add(this.hemi, this.sun, this.sun.target, this.ground)

    this.outline = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)), new THREE.LineBasicMaterial({ color: '#F59E0B' }))
    this.outline.visible = false
    this.scene.add(this.outline)

    const dom = this.renderer.domElement
    dom.addEventListener('pointerdown', this.onDown)
    dom.addEventListener('pointerup', this.onUp)
    dom.addEventListener('pointermove', this.onMove)
    dom.addEventListener('pointerleave', () => this.cb.onHover(null))

    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(el)
    this.resize()
    this.setTheme('light')
  }

  // ---------- public ----------
  setTheme(t: 'light' | 'dark') {
    this.theme = t
    const c = THEMES[t]
    this.scene.background = new THREE.Color(c.bg)
    this.sun.intensity = c.sun
    this.hemi.intensity = c.hemi
    this.buildGround()
    this.paint()
    this.render()
  }

  setData(snap: Snapshot, filter: Filter = this.filter) {
    this.snap = snap
    this.filter = filter
    const key = snap.blocks.map((b) => `${b.name}:${b.bay_count}x${b.row_count}`).join('|') + '#' + snap.stacks.length
    if (key !== this.layoutKey) {
      this.layoutKey = key
      this.computeLayout()
      this.buildGround()
    }
    this.buildInstances()
    if (!this.fitted && snap.blocks.length) { this.fit(); this.fitted = true }
    this.updateOutline()
    this.render()
  }

  setFilter(f: Filter) {
    this.filter = f
    this.paint()
    this.render()
  }

  select(name: string | null, focus = false) {
    this.selected = name
    this.updateOutline()
    if (name && focus) this.focus(name)
    this.render()
  }

  focus(name: string) {
    const p = this.pos.get(name)
    if (!p) return
    const dir = this.camera.position.clone().sub(this.controls.target).normalize()
    this.controls.target.set(p.x, p.y, p.z)
    this.camera.position.copy(new THREE.Vector3(p.x, p.y, p.z).addScaledVector(dir, 60))
    this.controls.update()
    this.render()
  }

  fit() {
    const box = new THREE.Box3()
    for (const o of this.origin.values()) { box.expandByPoint(new THREE.Vector3(o.x, 0, o.z)); box.expandByPoint(new THREE.Vector3(o.x + o.w, 0, o.z + o.d)) }
    if (box.isEmpty()) return
    const c = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const dist = Math.max(size.x, size.z) * 1.1 + 40
    this.controls.target.copy(c)
    this.camera.position.set(c.x + dist * 0.55, dist * 0.7, c.z + dist * 0.85)
    this.sun.position.set(c.x - 120, 220, c.z + 90)
    this.sun.target.position.copy(c)
    const half = Math.max(size.x, size.z) / 2 + 60
    const sc = this.sun.shadow.camera
    sc.left = -half; sc.right = half; sc.top = half; sc.bottom = -half; sc.far = 700
    sc.updateProjectionMatrix()
    this.controls.update()
    this.render()
  }

  dispose() {
    cancelAnimationFrame(this.raf)
    if (this.flashTimer) clearInterval(this.flashTimer)
    this.ro.disconnect()
    const dom = this.renderer.domElement
    dom.removeEventListener('pointerdown', this.onDown)
    dom.removeEventListener('pointerup', this.onUp)
    dom.removeEventListener('pointermove', this.onMove)
    this.controls.dispose()
    this.clearGroup(this.ground)
    this.mesh?.geometry.dispose()
    ;(this.mesh?.material as THREE.Material | undefined)?.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    dom.remove()
  }

  // ---------- layout ----------
  private computeLayout() {
    this.origin.clear()
    this.stackInfo.clear()
    const blocks = [...this.snap.blocks].sort((a, b) => String(a.block_code).localeCompare(String(b.block_code)))
    let z = 0
    let rowDepth = 0
    blocks.forEach((b, i) => {
      const col = i % COLUMNS
      if (col === 0 && i > 0) { z += rowDepth + BLOCK_GAP; rowDepth = 0 }
      const w = b.bay_count * SLOT
      const d = b.row_count * ROW
      this.origin.set(b.name, { x: this.colStart(blocks, col), z, w, d })
      rowDepth = Math.max(rowDepth, d)
    })
    for (const s of this.snap.stacks) this.stackInfo.set(s.name, { block: s.yard_block, bay: s.bay, row: s.row_no })
  }
  private colStart(blocks: any[], col: number) {
    // x offset of a column = widest block in earlier columns + gap
    let x = 0
    for (let c = 0; c < col; c++) {
      const w = Math.max(0, ...blocks.filter((_, i) => i % COLUMNS === c).map((b) => b.bay_count * SLOT))
      x += w + BLOCK_GAP
    }
    return x
  }

  private slotX(block: string, bay: number) {
    const o = this.origin.get(block)!
    return o.x + (bay - 0.5) * SLOT
  }
  private slotZ(block: string, row: number) {
    const o = this.origin.get(block)!
    return o.z + (row - 0.5) * ROW
  }

  // ---------- ground ----------
  private clearGroup(g: THREE.Group) {
    for (const ch of [...g.children]) {
      g.remove(ch)
      ch.traverse((o: any) => {
        o.geometry?.dispose?.()
        if (o.material) { o.material.map?.dispose?.(); o.material.dispose?.() }
      })
    }
  }

  private buildGround() {
    this.clearGroup(this.ground)
    const c = THEMES[this.theme]
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.MeshStandardMaterial({ color: c.ground, roughness: 1 }))
    plane.rotation.x = -Math.PI / 2
    plane.position.y = -0.06
    plane.receiveShadow = true
    this.ground.add(plane)
    for (const b of this.snap.blocks) {
      const o = this.origin.get(b.name)
      if (!o) continue
      const slab = new THREE.Mesh(new THREE.BoxGeometry(o.w + 2, 0.2, o.d + 2), new THREE.MeshStandardMaterial({ color: c.slab, roughness: 0.95 }))
      slab.position.set(o.x + o.w / 2, -0.1, o.z + o.d / 2)
      slab.receiveShadow = true
      this.ground.add(slab)
      const pts: number[] = []
      for (let i = 0; i <= b.bay_count; i++) pts.push(o.x + i * SLOT, 0.02, o.z, o.x + i * SLOT, 0.02, o.z + o.d)
      for (let r = 0; r <= b.row_count; r++) pts.push(o.x, 0.02, o.z + r * ROW, o.x + o.w, 0.02, o.z + r * ROW)
      const g = new THREE.BufferGeometry()
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
      this.ground.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: c.grid })))
      this.ground.add(this.label(`Block ${b.block_code}`, o.x + o.w / 2, o.z - 5, c.text))
    }
  }

  private label(text: string, x: number, z: number, color: string) {
    const cv = document.createElement('canvas')
    cv.width = 512; cv.height = 128
    const g = cv.getContext('2d')!
    g.font = '600 64px Inter, system-ui, sans-serif'
    g.fillStyle = color
    g.textAlign = 'center'; g.textBaseline = 'middle'
    g.fillText(text, 256, 64)
    const tex = new THREE.CanvasTexture(cv)
    tex.colorSpace = THREE.SRGBColorSpace
    const m = new THREE.Mesh(new THREE.PlaneGeometry(16, 4), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }))
    m.rotation.x = -Math.PI / 2
    m.position.set(x, 0.05, z)
    return m
  }

  // ---------- containers ----------
  private lineColour(line: string) {
    const l = this.snap.lines.find((x) => x.name === line)
    if (l?.colour) return new THREE.Color(l.colour)
    let h = 0
    for (const ch of line || '') h = (h * 31 + ch.charCodeAt(0)) >>> 0
    return new THREE.Color(PALETTE[h % PALETTE.length])
  }

  private buildInstances() {
    const list = this.snap.containers.filter((c) => c.yard_stack && this.stackInfo.has(c.yard_stack))
    if (!this.mesh || list.length > this.capacity) {
      if (this.mesh) { this.scene.remove(this.mesh); this.mesh.geometry.dispose(); (this.mesh.material as THREE.Material).dispose() }
      this.capacity = Math.max(512, Math.ceil(list.length * 1.5))
      const mat = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.1 })
      this.mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), mat, this.capacity)
      this.mesh.castShadow = true
      this.mesh.receiveShadow = true
      this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(this.capacity * 3), 3)
      this.scene.add(this.mesh)
    }
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    this.index = []
    this.pos.clear()
    const first = this.prevKey.size === 0
    const now = performance.now()
    const nextKey = new Map<string, string>()
    list.forEach((c, i) => {
      const a = this.stackInfo.get(c.yard_stack)!
      let x = this.slotX(a.block, a.bay)
      let len = Number(c.length_ft) >= 40 ? SLOT * 2 - 0.5 : SLOT - 0.5
      const b = c.partner_stack ? this.stackInfo.get(c.partner_stack) : null
      if (b) { x = (x + this.slotX(b.block, b.bay)) / 2; len = SLOT * 2 - 0.5 }
      const z = this.slotZ(a.block, a.row)
      const tier = Math.max(1, Number(c.tier) || 1)
      const y = (tier - 0.5) * TIER_H + 0.0
      m.compose(new THREE.Vector3(x, y, z), q, new THREE.Vector3(len, TIER_H - 0.12, WIDTH))
      this.mesh!.setMatrixAt(i, m)
      this.index.push(c.name)
      this.pos.set(c.name, { x, y, z, len })
      const k = `${c.yard_stack}/${c.tier}`
      nextKey.set(c.name, k)
      if (!first && this.prevKey.get(c.name) !== k) this.flashUntil.set(c.name, now + 3500)
    })
    this.prevKey = nextKey
    this.mesh.count = list.length
    this.mesh.instanceMatrix.needsUpdate = true
    this.mesh.computeBoundingSphere()
    this.paint()
    this.startFlashLoop()
  }

  private paint() {
    if (!this.mesh) return
    const t = THEMES[this.theme]
    const f = this.filter
    const faded = new THREE.Color(t.faded)
    const hold = new THREE.Color(t.hold)
    const flash = new THREE.Color(t.flash)
    const now = performance.now()
    const byName = new Map(this.snap.containers.map((c) => [c.name, c]))
    this.index.forEach((name, i) => {
      const c = byName.get(name)!
      const col = this.lineColour(c.shipping_line)
      if (c.cargo_status === 'Empty') col.lerp(new THREE.Color('#ffffff'), 0.4)
      if (c.is_on_hold) col.lerp(hold, 0.65)
      const match = (!f.line || c.shipping_line === f.line) && (!f.holdsOnly || c.is_on_hold) && (!f.cargo || c.cargo_status === f.cargo)
      if (!match) col.copy(faded)
      if ((this.flashUntil.get(name) || 0) > now) col.lerp(flash, 0.75)
      this.mesh!.setColorAt(i, col)
    })
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true
  }

  private startFlashLoop() {
    if (this.flashTimer || !this.flashUntil.size) return
    this.flashTimer = setInterval(() => {
      const now = performance.now()
      for (const [k, v] of this.flashUntil) if (v < now) this.flashUntil.delete(k)
      this.paint()
      this.render()
      if (!this.flashUntil.size && this.flashTimer) { clearInterval(this.flashTimer); this.flashTimer = null }
    }, 200)
  }

  private updateOutline() {
    const p = this.selected ? this.pos.get(this.selected) : null
    this.outline.visible = !!p
    if (p) {
      this.outline.position.set(p.x, p.y, p.z)
      this.outline.scale.set(p.len + 0.3, TIER_H - 0.05, WIDTH + 0.3)
    }
  }

  // ---------- input ----------
  private ndc(ev: PointerEvent) {
    const r = this.renderer.domElement.getBoundingClientRect()
    return new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1)
  }
  private pick(ev: PointerEvent): string | null {
    if (!this.mesh || !this.mesh.count) return null
    this.raycaster.setFromCamera(this.ndc(ev), this.camera)
    const hit = this.raycaster.intersectObject(this.mesh)[0]
    return hit && hit.instanceId !== undefined ? this.index[hit.instanceId] || null : null
  }
  private onDown = (ev: PointerEvent) => { this.down = { x: ev.clientX, y: ev.clientY } }
  private onUp = (ev: PointerEvent) => {
    const d = this.down
    this.down = null
    if (!d || Math.hypot(ev.clientX - d.x, ev.clientY - d.y) > 5) return
    const name = this.pick(ev)
    this.select(name)
    this.cb.onPick(name)
  }
  private onMove = (ev: PointerEvent) => {
    if (this.moving || this.down) return
    this.moving = true
    requestAnimationFrame(() => {
      this.moving = false
      const name = this.pick(ev)
      const r = this.renderer.domElement.getBoundingClientRect()
      this.renderer.domElement.style.cursor = name ? 'pointer' : 'grab'
      this.cb.onHover(name ? { name, x: ev.clientX - r.left, y: ev.clientY - r.top } : null)
    })
  }

  // ---------- render ----------
  private resize() {
    const w = this.el.clientWidth || 1
    const h = this.el.clientHeight || 1
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.render()
  }
  private render() {
    if (this.raf) return
    this.raf = requestAnimationFrame(() => {
      this.raf = 0
      this.renderer.render(this.scene, this.camera)
    })
  }
}
