import * as THREE from 'three'

// Draws everything in a yard layout except container blocks: ground areas, roads, buildings, gates, parks, fences and so on.
// Units are metres; x east, z south; rotation is degrees clockwise seen from above (three.js yaw = -rotation).

export interface LayoutItem {
  item_type: string
  label?: string | null
  yard_block?: string | null
  shape?: string
  x?: number
  z?: number
  rotation?: number
  length?: number
  width?: number
  height?: number
  surface?: string | null
  colour?: string | null
  direction?: string | null
  door_side?: string | null
  points?: string | null
  block_code?: string
  bay_count?: number
  row_count?: number
}
export interface Geometry { slot: number; row: number; tier: number; block_gap: number; car_bay: number; truck_bay: number }
export interface YardLayout { name: string | null; version: number; base_surface: string; automatic: boolean; items: LayoutItem[]; geometry: Geometry }
export type Theme = 'light' | 'dark'

const SURFACES: Record<Theme, Record<string, string>> = {
  light: { Asphalt: '#64748B', Concrete: '#CBD5E1', Gravel: '#A8A29E', Grass: '#86B97A', Sand: '#E7D8A8', Water: '#7DB6E0' },
  dark: { Asphalt: '#334155', Concrete: '#475569', Gravel: '#57534E', Grass: '#3F6B3A', Sand: '#8A7C52', Water: '#1E4F7A' },
}
const DEFAULTS: Record<string, { w: number; l: number; h: number }> = {
  Building: { w: 20, l: 30, h: 8 }, Gate: { w: 10, l: 12, h: 5 }, 'Car Park': { w: 20, l: 30, h: 0 }, 'Truck Park': { w: 24, l: 40, h: 0 },
  Heap: { w: 20, l: 30, h: 3 }, 'Rail Track': { w: 1.435, l: 100, h: 0 }, Crane: { w: 30, l: 12, h: 30 }, Weighbridge: { w: 4, l: 18, h: 0.5 },
  Road: { w: 12, l: 60, h: 0 }, Ground: { w: 40, l: 40, h: 0 }, Fence: { w: 0.2, l: 50, h: 2.4 }, 'Light Mast': { w: 0.5, l: 0.5, h: 25 },
  Tree: { w: 5, l: 5, h: 7 }, Label: { w: 16, l: 4, h: 0 },
}

export function surfaceColour(name: string | null | undefined, theme: Theme, fallback = 'Asphalt') {
  return SURFACES[theme][name || fallback] || SURFACES[theme][fallback]
}

export function parsePoints(text?: string | null): [number, number][] {
  const out: [number, number][] = []
  for (const line of (text || '').split('\n')) {
    const p = line.trim().replace(';', ',').split(',').map((s) => parseFloat(s))
    if (p.length === 2 && p.every((n) => Number.isFinite(n))) out.push([p[0], p[1]])
  }
  return out
}

/** Four corners (or the points) of an item in site coordinates, used to fit the camera. */
export function itemPoints(it: LayoutItem): [number, number][] {
  if (it.shape === 'Polygon' || it.shape === 'Polyline') return parsePoints(it.points)
  const d = DEFAULTS[it.item_type] || DEFAULTS.Ground
  const w = it.length || d.l, h = it.width || d.w
  const a = ((it.rotation || 0) * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a)
  return [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map(([lx, lz]) => [(it.x || 0) + lx * c - lz * s, (it.z || 0) + lx * s + lz * c])
}

export function layoutBounds(items: LayoutItem[]) {
  const box = new THREE.Box3()
  for (const it of items) for (const [x, z] of itemPoints(it)) box.expandByPoint(new THREE.Vector3(x, 0, z))
  return box
}

function textPlane(text: string, color: string, w: number, h: number) {
  const cv = document.createElement('canvas')
  cv.width = 512; cv.height = Math.max(64, Math.round((512 * h) / w))
  const g = cv.getContext('2d')!
  g.font = `600 ${Math.round(cv.height * 0.5)}px Inter, system-ui, sans-serif`
  g.fillStyle = color
  g.textAlign = 'center'; g.textBaseline = 'middle'
  g.fillText(text, 256, cv.height / 2, 500)
  const tex = new THREE.CanvasTexture(cv)
  tex.colorSpace = THREE.SRGBColorSpace
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }))
  m.rotation.x = -Math.PI / 2
  return m
}

const mat = (color: string, rough = 0.9) => new THREE.MeshStandardMaterial({ color, roughness: rough })
const lineMat = (color: string) => new THREE.LineBasicMaterial({ color })

function flatShape(pts: [number, number][], color: string, y: number) {
  const shape = new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, z)))
  const m = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshStandardMaterial({ color, roughness: 0.9, side: THREE.DoubleSide })) // double sided: the flip below turns the face downward
  m.rotation.x = Math.PI / 2 // shape (x, y) -> world (x, z)
  m.position.y = y
  m.receiveShadow = true
  return m
}

function box(w: number, h: number, d: number, color: string, x = 0, y = 0, z = 0, shadow = true) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color))
  m.position.set(x, y + h / 2, z)
  m.castShadow = shadow
  m.receiveShadow = true
  return m
}

function lines(pts: number[], color: string) {
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  return new THREE.LineSegments(g, lineMat(color))
}

/** A road strip along a polyline or a rectangle, with a dashed centre line (or arrows when one-way). */
function road(it: LayoutItem, theme: Theme, c: string, g: THREE.Group) {
  const width = it.width || DEFAULTS.Road.w
  const paint = theme === 'light' ? '#F8FAFC' : '#CBD5E1'
  let path: [number, number][]
  if (it.shape === 'Polyline') path = parsePoints(it.points)
  else {
    const l = (it.length || DEFAULTS.Road.l) / 2, a = ((it.rotation || 0) * Math.PI) / 180, co = Math.cos(a), si = Math.sin(a)
    path = [[-l, 0], [l, 0]].map(([lx, lz]) => [(it.x || 0) + lx * co - lz * si, (it.z || 0) + lx * si + lz * co])
  }
  for (let i = 0; i + 1 < path.length; i++) {
    const [x0, z0] = path[i], [x1, z1] = path[i + 1]
    const len = Math.hypot(x1 - x0, z1 - z0)
    if (len < 0.1) continue
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(len, width), mat(c))
    strip.rotation.x = -Math.PI / 2
    strip.rotation.z = Math.atan2(-(z1 - z0), x1 - x0)
    strip.position.set((x0 + x1) / 2, 0.012, (z0 + z1) / 2)
    strip.receiveShadow = true
    g.add(strip)
    const ux = (x1 - x0) / len, uz = (z1 - z0) / len
    const oneWay = it.direction === 'One-way forward' || it.direction === 'One-way reverse'
    const sign = it.direction === 'One-way reverse' ? -1 : 1
    const pts: number[] = []
    const step = oneWay ? 14 : 6
    for (let t = 1; t < len - 1; t += step) {
      if (!oneWay) { pts.push(x0 + ux * t, 0.03, z0 + uz * t, x0 + ux * Math.min(t + 3, len), 0.03, z0 + uz * Math.min(t + 3, len)); continue }
      const cx = x0 + ux * t, cz = z0 + uz * t, tx = ux * sign, tz = uz * sign, nx = -tz, nz = tx
      pts.push(cx - tx * 2, 0.03, cz - tz * 2, cx + tx * 2, 0.03, cz + tz * 2)
      pts.push(cx + tx * 2, 0.03, cz + tz * 2, cx + tx * 0.8 + nx * 1, 0.03, cz + tz * 0.8 + nz * 1)
      pts.push(cx + tx * 2, 0.03, cz + tz * 2, cx + tx * 0.8 - nx * 1, 0.03, cz + tz * 0.8 - nz * 1)
    }
    g.add(lines(pts, paint))
  }
}

/** Painted bays inside a park. Bay width comes from the yard geometry settings. */
function bays(len: number, wid: number, bayW: number, theme: Theme) {
  const pts: number[] = []
  const n = Math.max(1, Math.floor(len / bayW))
  const x0 = -(n * bayW) / 2
  const depth = Math.min(wid / 2 - 1, bayW * 2.2)
  for (const side of [-1, 1]) for (let i = 0; i <= n; i++) pts.push(x0 + i * bayW, 0.03, side * (wid / 2 - 0.3), x0 + i * bayW, 0.03, side * (wid / 2 - 0.3 - depth))
  return lines(pts, theme === 'light' ? '#F8FAFC' : '#CBD5E1')
}

export function buildLayoutItems(layout: YardLayout, theme: Theme, textColour: string): THREE.Group {
  const root = new THREE.Group()
  const g = layout.geometry
  const order = ['Ground', 'Road', 'Car Park', 'Truck Park', 'Rail Track', 'Heap', 'Weighbridge', 'Gate', 'Building', 'Fence', 'Crane', 'Light Mast', 'Tree', 'Label']
  const items = layout.items.filter((i) => i.item_type !== 'Block').sort((a, b) => order.indexOf(a.item_type) - order.indexOf(b.item_type))
  let layer = 0
  for (const it of items) {
    const d = DEFAULTS[it.item_type] || DEFAULTS.Ground
    const len = it.length || d.l, wid = it.width || d.w, hgt = it.height || d.h
    const grp = new THREE.Group()
    grp.position.set(it.x || 0, 0, it.z || 0)
    grp.rotation.y = (-(it.rotation || 0) * Math.PI) / 180
    const poly = it.shape === 'Polygon' ? parsePoints(it.points) : null
    const y = 0.004 + (layer++ % 50) * 0.0002 // keeps overlapping flat areas from flickering
    const colour = it.colour || ''
    switch (it.item_type) {
      case 'Ground': case 'Car Park': case 'Truck Park': case 'Heap': {
        const surf = colour || surfaceColour(it.surface, theme, it.item_type === 'Heap' ? 'Gravel' : it.item_type === 'Ground' ? 'Concrete' : 'Asphalt')
        if (poly && poly.length > 2) {
          if (it.item_type === 'Heap') {
            // a shaped heap is a flat-topped pile with the outline drawn
            const pile = new THREE.Mesh(new THREE.ExtrudeGeometry(new THREE.Shape(poly.map(([x, z]) => new THREE.Vector2(x, z))), { depth: hgt, bevelEnabled: false }), mat(colour || surfaceColour('Gravel', theme)))
            pile.rotation.x = Math.PI / 2
            pile.position.y = hgt
            pile.castShadow = true; pile.receiveShadow = true
            root.add(pile)
          } else root.add(flatShape(poly, surf, y))
          break
        }
        if (it.item_type === 'Heap') {
          const cone = new THREE.Mesh(new THREE.CylinderGeometry(wid * 0.18, Math.min(len, wid) / 2, hgt, 20), mat(colour || surfaceColour('Gravel', theme)))
          cone.scale.set(len / Math.min(len, wid), 1, wid / Math.min(len, wid))
          cone.position.y = hgt / 2
          cone.castShadow = true
          grp.add(cone)
        } else {
          const p = new THREE.Mesh(new THREE.PlaneGeometry(len, wid), mat(surf))
          p.rotation.x = -Math.PI / 2
          p.position.y = y
          p.receiveShadow = true
          grp.add(p)
          if (it.item_type === 'Car Park') grp.add(bays(len, wid, g.car_bay, theme))
          if (it.item_type === 'Truck Park') grp.add(bays(len, wid, g.truck_bay, theme))
        }
        root.add(grp)
        break
      }
      case 'Road': road(it, theme, colour || surfaceColour(it.surface, theme, 'Asphalt'), root); break
      case 'Building': {
        const wall = colour || (theme === 'light' ? '#E2E8F0' : '#475569')
        if (poly && poly.length > 2) {
          const shape = new THREE.Shape(poly.map(([x, z]) => new THREE.Vector2(x, z)))
          const m = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: hgt, bevelEnabled: false }), mat(wall))
          m.rotation.x = Math.PI / 2
          m.position.y = hgt
          m.castShadow = true; m.receiveShadow = true
          root.add(m)
          break
        }
        grp.add(box(len, hgt, wid, wall))
        grp.add(box(len + 0.8, 0.5, wid + 0.8, theme === 'light' ? '#94A3B8' : '#1E293B', 0, hgt))
        const door = box(Math.min(3, len / 3), Math.min(3, hgt * 0.7), 0.15, '#334155', 0, 0, wid / 2 + 0.05, false)
        grp.add(door)
        for (let i = -1; i <= 1; i += 2) grp.add(box(Math.min(3, len / 4), 1.2, 0.12, '#93C5FD', i * len * 0.28, hgt * 0.45, wid / 2 + 0.05, false))
        if (it.label) { const t = textPlane(it.label, textColour, Math.min(len, 18), 3); t.position.set(0, hgt + 0.9, 0); grp.add(t) }
        root.add(grp)
        break
      }
      case 'Gate': {
        // A drive-through gate: lanes about 4 m wide separated by booth islands, a canopy over the booths and a barrier arm at the
        // entry end of every lane. Trucks drive toward +z (the way the arrow points on the plan); the barriers are on the -z side.
        const n = Math.max(1, Math.round(len / 4))
        const laneW = len / n
        const depth = Math.min(wid, 12)
        const asphalt = colour || (theme === 'light' ? '#64748B' : '#334155')
        const kerb = theme === 'light' ? '#E2E8F0' : '#64748B'
        const paint = theme === 'light' ? '#F8FAFC' : '#CBD5E1'
        grp.add(box(len, 0.05, wid, asphalt, 0, 0, 0, false))
        const dash: number[] = []
        for (let i = 0; i < n; i++) {
          const cx = -len / 2 + (i + 0.5) * laneW
          for (let z = -wid / 2 + 1; z < wid / 2 - 1; z += 4) dash.push(cx, 0.08, z, cx, 0.08, Math.min(z + 2, wid / 2 - 1))
        }
        grp.add(lines(dash, paint))
        const zb = -depth / 2 - 0.4 // barrier line
        for (let i = 0; i <= n; i++) {
          const x = -len / 2 + i * laneW
          const edge = i === 0 || i === n
          const iw = edge ? 0.5 : 1.6
          const ix = edge ? x + (i === 0 ? iw / 2 : -iw / 2) : x
          grp.add(box(iw, 0.22, depth + 1, kerb, ix, 0.02, 0))
          grp.add(box(0.3, 4.8, 0.3, '#64748B', ix, 0.24, depth * 0.38))
          grp.add(box(0.3, 4.8, 0.3, '#64748B', ix, 0.24, -depth * 0.38))
          if (!edge) {
            grp.add(box(1.3, 2.7, 2.8, '#F1F5F9', x, 0.24, 0))
            grp.add(box(1.36, 0.8, 2.0, '#93C5FD', x, 1.45, 0, false))
          }
        }
        grp.add(box(len + 1.6, 0.45, depth * 0.85, colour ? colour : '#0EA5E9', 0, 5.0, 0))
        for (let i = 0; i < n; i++) {
          const x0 = -len / 2 + i * laneW + (i === 0 ? 0.5 : 0.8) // pole side of this lane
          const al = laneW - (i === 0 ? 0.5 : 0.8) - 0.5
          grp.add(box(0.3, 1.1, 0.3, '#475569', x0 - 0.15, 0.02, zb))
          for (let k = 0; k < 4; k++) grp.add(box(al / 4, 0.14, 0.14, k % 2 ? '#F8FAFC' : '#EF4444', x0 + (k + 0.5) * (al / 4), 1.0, zb, false))
        }
        if (it.label) { const t = textPlane(it.label, textColour, Math.min(len + 4, 14), 3); t.position.set(0, 5.5, 0); grp.add(t) }
        root.add(grp)
        break
      }
      case 'Rail Track': {
        const gauge = wid || 1.435
        const rail = theme === 'light' ? '#475569' : '#94A3B8'
        const sl = theme === 'light' ? '#78716C' : '#57534E'
        const ballast = new THREE.Mesh(new THREE.PlaneGeometry(len, gauge + 1.6), mat(theme === 'light' ? '#A8A29E' : '#44403C'))
        ballast.rotation.x = -Math.PI / 2; ballast.position.y = y; ballast.receiveShadow = true
        grp.add(ballast)
        for (const s of [-1, 1]) grp.add(box(len, 0.16, 0.12, rail, 0, 0.12, s * gauge / 2, false))
        const n = Math.floor(len / 0.65)
        const sleepers = new THREE.InstancedMesh(new THREE.BoxGeometry(0.26, 0.12, gauge + 0.9), mat(sl), n)
        const mm = new THREE.Matrix4()
        for (let i = 0; i < n; i++) { mm.setPosition(-len / 2 + 0.3 + i * 0.65, 0.07, 0); sleepers.setMatrixAt(i, mm) }
        grp.add(sleepers)
        root.add(grp)
        break
      }
      case 'Crane': {
        // portal frame spanning a rail gauge, boom out over the quay
        const span = wid || 30, legH = hgt || 30
        const steel = colour || '#F59E0B'
        for (const s of [-1, 1]) for (const e of [-1, 1]) grp.add(box(1, legH, 1, steel, e * len / 2, 0, s * span / 2))
        grp.add(box(len + 2, 1.6, span + 2, steel, 0, legH, 0))
        grp.add(box(len * 0.6, 1.2, span + 40, steel, 0, legH + 1.6, -20))
        root.add(grp)
        break
      }
      case 'Weighbridge': {
        grp.add(box(len, 0.35, wid, theme === 'light' ? '#94A3B8' : '#475569', 0, 0, 0))
        grp.add(box(1.2, 2, 1.2, '#F1F5F9', 0, 0, wid / 2 + 1.2))
        root.add(grp)
        break
      }
      case 'Fence': {
        const path: [number, number][] = it.shape === 'Polyline' || it.shape === 'Polygon' ? parsePoints(it.points) : [[-len / 2, 0], [len / 2, 0]]
        const a = ((it.rotation || 0) * Math.PI) / 180, co = Math.cos(a), si = Math.sin(a)
        const pts = it.shape === 'Polyline' || it.shape === 'Polygon' ? path : path.map(([lx, lz]) => [(it.x || 0) + lx * co - lz * si, (it.z || 0) + lx * si + lz * co] as [number, number])
        const closed = it.shape === 'Polygon'
        const post = new THREE.Mesh(new THREE.BoxGeometry(0.12, hgt, 0.12), mat('#64748B'))
        const seg: number[] = []
        const posts: [number, number][] = []
        const n = pts.length + (closed ? 1 : 0)
        for (let i = 0; i + 1 < n; i++) {
          const [x0, z0] = pts[i], [x1, z1] = pts[(i + 1) % pts.length]
          const l = Math.hypot(x1 - x0, z1 - z0)
          const k = Math.max(1, Math.round(l / 3))
          for (let j = 0; j <= k; j++) posts.push([x0 + ((x1 - x0) * j) / k, z0 + ((z1 - z0) * j) / k])
          for (const hh of [hgt * 0.35, hgt * 0.7, hgt]) seg.push(x0, hh, z0, x1, hh, z1)
        }
        const inst = new THREE.InstancedMesh(post.geometry, post.material, Math.max(1, posts.length))
        const mm = new THREE.Matrix4()
        posts.forEach(([x, z], i) => { mm.setPosition(x, hgt / 2, z); inst.setMatrixAt(i, mm) })
        root.add(inst, lines(seg, '#94A3B8'))
        break
      }
      case 'Light Mast': {
        grp.add(box(0.35, hgt, 0.35, '#64748B', 0, 0, 0))
        const head = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.5, 1.2), new THREE.MeshStandardMaterial({ color: '#FEF3C7', emissive: '#FDE68A', emissiveIntensity: theme === 'dark' ? 1.2 : 0.25 }))
        head.position.y = hgt
        grp.add(head)
        root.add(grp)
        break
      }
      case 'Tree': {
        grp.add(box(0.4, hgt * 0.35, 0.4, '#78350F', 0, 0, 0))
        const crown = new THREE.Mesh(new THREE.SphereGeometry(wid / 2, 14, 10), mat(colour || (theme === 'light' ? '#4D8B45' : '#2F5D2A')))
        crown.position.y = hgt * 0.35 + wid * 0.35
        crown.castShadow = true
        grp.add(crown)
        root.add(grp)
        break
      }
      case 'Label': {
        const t = textPlane(it.label || '', colour || textColour, len, wid)
        t.position.y = 0.06
        grp.add(t)
        root.add(grp)
        break
      }
    }
  }
  return root
}
