'use client'

import { useEffect, useMemo, useRef } from 'react'
import { Canvas, invalidate, useFrame, useThree } from '@react-three/fiber'
import { ContactShadows, RoundedBox } from '@react-three/drei'
import * as THREE from 'three'

/**
 * The intelligence engine: six slabs that stack in the hero and separate on
 * scroll into the sequence a complaint travels.
 *
 * Complaint · AI (sand, matte: pencil) · Knowledge · Rules · Validation
 * (espresso: ink, locks in last) · Resolution.
 *
 * Rendering is on demand: nothing draws unless scroll progress or the pointer
 * moves. Geometry is six rounded boxes. DPR is clamped. No post-processing,
 * no environment map, no particles.
 */

export type Progress = { value: number; pointer: { x: number; y: number } }

export const SLABS = [
  { key: 'complaint',  label: 'Complaint',   color: '#FDFBF7', rough: 0.95, metal: 0.0 },
  // The AI slab is the pencil: chalky, matte, the softest thing in the stack.
  { key: 'ai',         label: 'AI proposes', color: '#E4D7C2', rough: 1.0,  metal: 0.0 },
  { key: 'knowledge',  label: 'Knowledge',   color: '#CDBB9F', rough: 0.8,  metal: 0.02 },
  { key: 'rules',      label: 'Rules',       color: '#93795F', rough: 0.62, metal: 0.05 },
  // The validation slab is the ink: darkest, glossiest, the one that catches
  // the key light when it locks into place.
  { key: 'validation', label: 'Validation',  color: '#241A13', rough: 0.3,  metal: 0.18 },
  { key: 'resolution', label: 'Resolution',  color: '#F4EEE4', rough: 0.88, metal: 0.0 },
] as const

const SLAB_W = 2.72
const SLAB_H = 0.115
const SLAB_D = 1.74
const STACK_GAP = 0.185

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const smooth = (t: number) => t * t * (3 - 2 * t)

function Slabs({ progress }: { progress: Progress }) {
  const group = useRef<THREE.Group>(null)
  const refs = useRef<Array<THREE.Mesh | null>>([])
  const settled = useRef(false)

  const targets = useMemo(() => {
    const stacked = SLABS.map((_, i) => new THREE.Vector3(0, (i - 2.5) * STACK_GAP, 0))
    const spread = SLABS.map((_, i) => new THREE.Vector3((i - 2.5) * 0.98, 0.05 + Math.sin(i * 1.3) * 0.06, (i - 2.5) * -0.22))
    return { stacked, spread }
  }, [])

  useFrame(() => {
    const p = smooth(clamp01(progress.value))
    let moving = false
    refs.current.forEach((mesh, i) => {
      if (!mesh) return
      // The validation slab holds its place until the others have separated,
      // then drops into line: the rules confirm last, and visibly.
      const local = i === 4 ? smooth(clamp01((p - 0.45) / 0.55)) : smooth(clamp01((p - i * 0.06) / 0.7))
      const target = new THREE.Vector3().lerpVectors(targets.stacked[i], targets.spread[i], local)
      if (i === 4 && p > 0.05 && p < 0.9) target.y += (1 - local) * 0.55 * Math.sin(p * Math.PI)
      const before = mesh.position.distanceTo(target)
      mesh.position.lerp(target, 0.18)
      const rotTarget = local * -0.12
      mesh.rotation.x += (rotTarget - mesh.rotation.x) * 0.18
      mesh.rotation.y += ((1 - local) * (i % 2 ? 0.05 : -0.05) - mesh.rotation.y) * 0.18
      if (before > 0.0015) moving = true
    })
    if (group.current) {
      const rx = -0.22 + progress.pointer.y * 0.05
      const ry = 0.55 - p * 0.35 + progress.pointer.x * 0.08
      const gx = group.current.rotation.x, gy = group.current.rotation.y
      group.current.rotation.x += (rx - gx) * 0.12
      group.current.rotation.y += (ry - gy) * 0.12
      if (Math.abs(rx - gx) > 0.0008 || Math.abs(ry - gy) > 0.0008) moving = true
      const scale = 1 - p * 0.12
      group.current.scale.setScalar(group.current.scale.x + (scale - group.current.scale.x) * 0.15)
    }
    settled.current = !moving
    if (moving) invalidate()
  })

  return (
    <group ref={group} rotation={[-0.22, 0.55, 0]}>
      {SLABS.map((s, i) => (
        <RoundedBox
          key={s.key}
          ref={(m) => { refs.current[i] = m }}
          args={[SLAB_W, SLAB_H, SLAB_D]}
          radius={0.035}
          smoothness={3}
          castShadow
          receiveShadow
        >
          <meshStandardMaterial color={s.color} roughness={s.rough} metalness={s.metal} />
        </RoundedBox>
      ))}
    </group>
  )
}

function Lights() {
  return (
    <>
      {/* Warm studio: one key with a shadow, a cool-ish fill to keep the
          cream from going muddy, and a rim that draws the slab edges. */}
      <ambientLight intensity={0.55} color="#fff3e3" />
      <directionalLight
        position={[4.5, 7, 3.5]}
        intensity={2.3}
        color="#fff0d8"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0006}
      />
      <directionalLight position={[-5, 2.5, 2]} intensity={0.55} color="#e6dccd" />
      <directionalLight position={[0, 1.5, -5]} intensity={0.85} color="#ffe9cc" />
      <pointLight position={[1.6, 1.2, 2.4]} intensity={7} distance={9} decay={2} color="#fff6e8" />
    </>
  )
}

/** Wake the demand-mode loop whenever the page scrolls or the pointer moves. */
function Wake({ progress }: { progress: Progress }) {
  const { gl } = useThree()
  useEffect(() => {
    const el = gl.domElement
    let raf = 0
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      progress.pointer.x = ((e.clientX - r.left) / r.width - 0.5) * 2
      progress.pointer.y = ((e.clientY - r.top) / r.height - 0.5) * 2
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; invalidate() })
    }
    const onLeave = () => { progress.pointer.x = 0; progress.pointer.y = 0; invalidate() }
    el.addEventListener('pointermove', onMove, { passive: true })
    el.addEventListener('pointerleave', onLeave)
    return () => { el.removeEventListener('pointermove', onMove); el.removeEventListener('pointerleave', onLeave) }
  }, [gl, progress])
  return null
}

export default function Engine({ progress, className }: { progress: Progress; className?: string }) {
  return (
    <Canvas
      className={className}
      frameloop="demand"
      dpr={[1, 1.75]}
      // "percentage" is PCFShadowMap. Bare `shadows` asks R3F for
      // PCFSoftShadowMap, which three r186 removed and logs an error about.
      shadows="percentage"
      camera={{ position: [0, 2.05, 6.0], fov: 33, near: 0.1, far: 30 }}
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      onCreated={({ gl, camera }) => {
        gl.setClearColor(0x000000, 0)
        gl.toneMapping = THREE.ACESFilmicToneMapping
        gl.toneMappingExposure = 1.16
        camera.lookAt(0, 0, 0)
      }}
    >
      <Lights />
      <Slabs progress={progress} />
      <ContactShadows position={[0, -0.72, 0]} opacity={0.44} scale={10} blur={2.9} far={3.4} color="#2a1f17" frames={1} />
      <Wake progress={progress} />
    </Canvas>
  )
}
