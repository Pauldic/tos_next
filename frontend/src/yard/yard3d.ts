import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { buildLayoutItems, layoutBounds, surfaceColour, type YardLayout } from './layoutRender'
import { LabelAtlas, REAL, buildContainerGeometry, buildContainerMaterial } from './containerModel'

// 1 unit = 1 metre. A slot is one 20 ft bay; a 40 ft container spans two neighbouring bays.
const WIDTH = 2.44
// Sizes of a slot, row and tier come from the terminal's yard geometry (company settings) with each snapshot.
const DEFAULT_GEOMETRY = { slot: 6.4, row: 3.2, tier: 2.7, block_gap: 16, car_bay: 2.5, truck_bay: 4 }
// Level of detail: containers nearer than NEAR_DIST (at most MAX_NEAR of them) are drawn with ribs, door rods and name labels.
// Everything further away is a plain box, so thousands of containers stay smooth.
const NEAR_DIST = 90
const MAX_NEAR = 120
const UP = new THREE.Vector3(0, 1, 0)
const PALETTE = ['#2563EB', '#0EA5E9', '#14B8A6', '#F97316', '#8B5CF6', '#EC4899', '#84CC16', '#EAB308']

export interface Snapshot {
  blocks: any[]
  stacks: any[]
  containers: any[]
  lines: any[]
  layout?: YardLayout | null
}
export interface Filter {
  line?: string | null
  holdsOnly?: boolean
  cargo?: 'Full' | 'Empty' | null
}
interface Pos { x: number; y: number; z: number; len: number; yaw: number }

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
  private mesh: THREE.InstancedMesh | null = null // invisible: one box per container, used for picking
  private far: THREE.InstancedMesh | null = null // visible plain boxes for distant containers
  private near20: THREE.InstancedMesh
  private near40: THREE.InstancedMesh
  private decals: THREE.Mesh[] = []
  private decalSlot: number[] = []
  private decalMat: THREE.MeshStandardMaterial
  private atlas = new LabelAtlas()
  private lodTimer: ReturnType<typeof setTimeout> | null = null
  private items: { name: string; x: number; y: number; z: number; len: number; yaw: number; flip: boolean }[] = []
  private byName = new Map<string, any>()
  private capacity = 0
  private outline: THREE.LineSegments
  private sun: THREE.DirectionalLight
  private hemi: THREE.HemisphereLight
  private raf = 0
  private flashTimer: ReturnType<typeof setInterval> | null = null
  private ro: ResizeObserver
  private theme: 'light' | 'dark' = 'light'

  private snap: Snapshot = { blocks: [], stacks: [], containers: [], lines: [], layout: null }
  private g = DEFAULT_GEOMETRY
  private layoutGroup = new THREE.Group()
  private filter: Filter = {}
  private layoutKey = ''
  private stackInfo = new Map<string, { block: string; bay: number; row: number }>()
  private origin = new Map<string, { cx: number; cz: number; w: number; d: number; rot: number; flip: boolean }>()
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
    this.controls.addEventListener('change', () => { this.render(); this.scheduleLod() })

    const bodyMat = buildContainerMaterial()
    this.near20 = new THREE.InstancedMesh(buildContainerGeometry(REAL.l20), bodyMat, MAX_NEAR)
    this.near40 = new THREE.InstancedMesh(buildContainerGeometry(REAL.l40), bodyMat, MAX_NEAR)
    for (const m of [this.near20, this.near40]) {
      m.castShadow = true
      m.receiveShadow = true
      m.count = 0
      m.frustumCulled = false
      this.scene.add(m)
    }
    this.decalMat = new THREE.MeshStandardMaterial({
      map: this.atlas.texture, transparent: true, alphaTest: 0.03, depthWrite: false, roughness: 0.6, metalness: 0,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    })

    this.hemi = new THREE.HemisphereLight('#ffffff', '#94a3b8', 1)
    this.sun = new THREE.DirectionalLight('#ffffff', 2)
    this.sun.position.set(-120, 220, 90)
    this.sun.castShadow = true
    this.sun.shadow.mapSize.set(2048, 2048)
    this.scene.add(this.hemi, this.sun, this.sun.target, this.ground, this.layoutGroup)

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
    const key = JSON.stringify(snap.layout || null) + '#' + snap.blocks.map((b) => `${b.name}:${b.bay_count}x${b.row_count}`).join('|') + '#' + snap.stacks.length
    if (key !== this.layoutKey) {
      this.layoutKey = key
      this.computeLayout()
      this.buildGround()
    }
    this.buildInstances()
    if (!this.fitted && (snap.blocks.length || snap.layout?.items.length)) { this.fit(); this.fitted = true }
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
    const box = layoutBounds(this.snap.layout?.items || [])
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
    this.clearGroup(this.layoutGroup)
    if (this.lodTimer) clearTimeout(this.lodTimer)
    this.mesh?.geometry.dispose()
    ;(this.mesh?.material as THREE.Material | undefined)?.dispose()
    this.far?.geometry.dispose()
    ;(this.far?.material as THREE.Material | undefined)?.dispose()
    for (const m of [this.near20, this.near40]) { m.geometry.dispose(); (m.material as THREE.Material).dispose() }
    for (const d of this.decals) d.geometry.dispose()
    this.decalMat.dispose()
    this.atlas.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    dom.remove()
  }

  // ---------- layout ----------
  private computeLayout() {
    this.origin.clear()
    this.stackInfo.clear()
    const lay = this.snap.layout
    this.g = lay?.geometry || DEFAULT_GEOMETRY
    for (const it of lay?.items || []) {
      if (it.item_type !== 'Block' || !it.yard_block) continue
      const b = this.snap.blocks.find((x) => x.name === it.yard_block)
      if (!b) continue
      this.origin.set(it.yard_block, {
        cx: it.x || 0, cz: it.z || 0, w: b.bay_count * this.g.slot, d: b.row_count * this.g.row,
        rot: ((it.rotation || 0) * Math.PI) / 180, flip: it.door_side !== 'Higher bay end',
      })
    }
    for (const s of this.snap.stacks) if (this.origin.has(s.yard_block)) this.stackInfo.set(s.name, { block: s.yard_block, bay: s.bay, row: s.row_no })
  }

  /** Site position of the centre of a bay/row slot, turning the block's local grid by its rotation. */
  private slot(block: string, bay: number, row: number) {
    const o = this.origin.get(block)!
    const lx = (bay - 0.5) * this.g.slot - o.w / 2
    const lz = (row - 0.5) * this.g.row - o.d / 2
    const c = Math.cos(o.rot), s = Math.sin(o.rot)
    return { x: o.cx + lx * c - lz * s, z: o.cz + lx * s + lz * c }
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
    this.clearGroup(this.layoutGroup)
    const c = THEMES[this.theme]
    const base = this.snap.layout?.base_surface
    const baseColour = base && base !== 'Default' ? surfaceColour(base, this.theme) : c.ground
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.MeshStandardMaterial({ color: baseColour, roughness: 1 }))
    plane.rotation.x = -Math.PI / 2
    plane.position.y = -0.06
    plane.receiveShadow = true
    this.ground.add(plane)
    if (this.snap.layout) this.layoutGroup.add(buildLayoutItems(this.snap.layout, this.theme, c.text))
    for (const b of this.snap.blocks) {
      const o = this.origin.get(b.name)
      if (!o) continue
      const grp = new THREE.Group()
      grp.position.set(o.cx, 0, o.cz)
      grp.rotation.y = -o.rot
      const slab = new THREE.Mesh(new THREE.BoxGeometry(o.w + 2, 0.2, o.d + 2), new THREE.MeshStandardMaterial({ color: c.slab, roughness: 0.95 }))
      slab.position.set(0, -0.1, 0)
      slab.receiveShadow = true
      grp.add(slab)
      const pts: number[] = []
      for (let i = 0; i <= b.bay_count; i++) pts.push(-o.w / 2 + i * this.g.slot, 0.02, -o.d / 2, -o.w / 2 + i * this.g.slot, 0.02, o.d / 2)
      for (let r = 0; r <= b.row_count; r++) pts.push(-o.w / 2, 0.02, -o.d / 2 + r * this.g.row, o.w / 2, 0.02, -o.d / 2 + r * this.g.row)
      const g = new THREE.BufferGeometry()
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
      grp.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: c.grid })))
      grp.add(this.label(`Block ${b.block_code}`, 0, -o.d / 2 - 5, c.text))
      this.ground.add(grp)
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
      if (this.far) { this.scene.remove(this.far); this.far.geometry.dispose(); (this.far.material as THREE.Material).dispose() }
      this.capacity = Math.max(512, Math.ceil(list.length * 1.5))
      this.mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial(), this.capacity)
      this.mesh.visible = false // raycasting still works on an invisible mesh
      this.scene.add(this.mesh)
      this.far = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.1 }), this.capacity)
      this.far.castShadow = true
      this.far.receiveShadow = true
      this.far.frustumCulled = false
      this.far.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(this.capacity * 3), 3)
      this.scene.add(this.far)
    }
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    this.index = []
    this.items = []
    this.pos.clear()
    this.byName = new Map(this.snap.containers.map((c) => [c.name, c]))
    const first = this.prevKey.size === 0
    const now = performance.now()
    const nextKey = new Map<string, string>()
    list.forEach((c, i) => {
      const a = this.stackInfo.get(c.yard_stack)!
      const o = this.origin.get(a.block)!
      const sa = this.slot(a.block, a.bay, a.row)
      let x = sa.x, z = sa.z
      let len = Number(c.length_ft) >= 40 ? this.g.slot * 2 - 0.5 : this.g.slot - 0.5
      const b = c.partner_stack ? this.stackInfo.get(c.partner_stack) : null
      if (b) { const sb = this.slot(b.block, b.bay, b.row); x = (x + sb.x) / 2; z = (z + sb.z) / 2; len = this.g.slot * 2 - 0.5 }
      const tier = Math.max(1, Number(c.tier) || 1)
      const y = (tier - 1) * this.g.tier + REAL.h / 2
      const yaw = -o.rot
      q.setFromAxisAngle(UP, yaw)
      m.compose(new THREE.Vector3(x, y, z), q, new THREE.Vector3(len, REAL.h, WIDTH))
      this.mesh!.setMatrixAt(i, m)
      this.index.push(c.name)
      this.items.push({ name: c.name, x, y, z, len, yaw, flip: o.flip })
      this.pos.set(c.name, { x, y, z, len, yaw })
      const k = `${c.yard_stack}/${c.tier}`
      nextKey.set(c.name, k)
      if (!first && this.prevKey.get(c.name) !== k) this.flashUntil.set(c.name, now + 3500)
    })
    this.prevKey = nextKey
    this.mesh.count = list.length
    this.mesh.instanceMatrix.needsUpdate = true
    this.mesh.computeBoundingSphere()
    this.lod()
    this.startFlashLoop()
  }

  /** The colour a container shows right now: its line, then empty / hold / filter / just-moved tints. */
  private colourOf(name: string) {
    const t = THEMES[this.theme]
    const f = this.filter
    const c = this.byName.get(name)
    const col = this.lineColour(c.shipping_line)
    if (c.cargo_status === 'Empty') col.lerp(new THREE.Color('#ffffff'), 0.4)
    if (c.is_on_hold) col.lerp(new THREE.Color(t.hold), 0.65)
    const match = (!f.line || c.shipping_line === f.line) && (!f.holdsOnly || c.is_on_hold) && (!f.cargo || c.cargo_status === f.cargo)
    if (!match) col.copy(new THREE.Color(t.faded))
    if ((this.flashUntil.get(name) || 0) > performance.now()) col.lerp(new THREE.Color(t.flash), 0.75)
    return col
  }

  private scheduleLod() {
    if (this.lodTimer) return
    this.lodTimer = setTimeout(() => { this.lodTimer = null; this.lod(); this.render() }, 120)
  }

  private decal(i: number) {
    let d = this.decals[i]
    if (!d) {
      d = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.decalMat)
      d.matrixAutoUpdate = false
      d.frustumCulled = false
      this.scene.add(d)
      this.decals[i] = d
      this.decalSlot[i] = -1
    }
    return d
  }

  /** Decides which containers are close enough for full detail and writes every instance's position and colour. */
  private lod() {
    if (!this.far || !this.mesh) return
    const cam = this.camera.position
    const nearIdx: { i: number; d: number }[] = []
    this.items.forEach((it, i) => {
      const d = Math.hypot(it.x - cam.x, it.y - cam.y, it.z - cam.z)
      if (d < NEAR_DIST) nearIdx.push({ i, d })
    })
    nearIdx.sort((a, b) => a.d - b.d)
    const near = new Set(nearIdx.slice(0, MAX_NEAR).map((n) => n.i))

    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const flip = new THREE.Quaternion()
    const sideBack = new THREE.Quaternion().setFromAxisAngle(UP, Math.PI)
    const none = new THREE.Quaternion()
    const one = new THREE.Vector3(1, 1, 1)
    let nFar = 0, n20 = 0, n40 = 0, nDecal = 0
    this.atlas.beginFrame()

    this.items.forEach((it, i) => {
      const col = this.colourOf(it.name)
      q.setFromAxisAngle(UP, it.yaw)
      flip.setFromAxisAngle(UP, it.yaw + (it.flip ? Math.PI : 0))
      if (!near.has(i)) {
        m.compose(new THREE.Vector3(it.x, it.y, it.z), q, new THREE.Vector3(it.len, REAL.h, WIDTH))
        this.far!.setMatrixAt(nFar, m)
        this.far!.setColorAt(nFar, col)
        nFar++
        return
      }
      const is40 = it.len > this.g.slot
      const mesh = is40 ? this.near40 : this.near20
      const k = is40 ? n40++ : n20++
      m.compose(new THREE.Vector3(it.x, it.y, it.z), flip, new THREE.Vector3(it.len / (is40 ? REAL.l40 : REAL.l20), 1, 1))
      mesh.setMatrixAt(k, m)
      mesh.setColorAt(k, col)

      // name and number on both long sides
      const c = this.byName.get(it.name)
      const line = this.snap.lines.find((l) => l.name === c.shipping_line)
      const lum = 0.2126 * col.r + 0.7152 * col.g + 0.0722 * col.b
      const slot = this.atlas.ensure(it.name, line?.line_name || c.shipping_line || '', lum > 0.3 ? '#111827' : '#FFFFFF')
      if (slot < 0) return
      const w = Math.min(it.len * 0.55, 5.4)
      const mc = new THREE.Matrix4().compose(new THREE.Vector3(it.x, it.y, it.z), flip, one)
      for (const side of [1, -1]) {
        const ml = new THREE.Matrix4().compose(
          new THREE.Vector3(-it.len * 0.12, 0.22, side * (REAL.w / 2 + 0.012)),
          side === 1 ? none : sideBack,
          new THREE.Vector3(w, w / 4, 1),
        )
        const d = this.decal(nDecal)
        d.matrix.copy(mc).multiply(ml)
        d.matrixWorld.copy(d.matrix)
        d.visible = true
        if (this.decalSlot[nDecal] !== slot) {
          const r = this.atlas.uv(slot)
          const uv = (d.geometry as THREE.PlaneGeometry).getAttribute('uv') as THREE.BufferAttribute
          uv.setXY(0, r.u0, r.v0 + r.dv)
          uv.setXY(1, r.u0 + r.du, r.v0 + r.dv)
          uv.setXY(2, r.u0, r.v0)
          uv.setXY(3, r.u0 + r.du, r.v0)
          uv.needsUpdate = true
          this.decalSlot[nDecal] = slot
        }
        nDecal++
      }
    })
    for (let i = nDecal; i < this.decals.length; i++) this.decals[i].visible = false
    this.far.count = nFar
    this.near20.count = n20
    this.near40.count = n40
    for (const mesh of [this.far, this.near20, this.near40]) {
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    }
    this.atlas.flush()
  }

  private paint() {
    this.lod()
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
      this.outline.rotation.y = p.yaw
      this.outline.scale.set(p.len + 0.3, REAL.h + 0.1, WIDTH + 0.3)
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
