import React, { useRef, useLayoutEffect, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, ContactShadows, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

// ─── Reveal ────────────────────────────────────────────────────────────────────
const REVEAL_DURATION    = 1.6;
const REVEAL_Y_START     = -4.5;
const REVEAL_Y_REST      = -1;
const REVEAL_Y_OVERSHOOT = REVEAL_Y_REST + 0.22;

// ─── Top-of-page idle state ────────────────────────────────────────────────────
// When scrollY is near 0 the car levitates and tracks the pointer.
const IDLE_ROT_SPEED     = 0.55;    // rad/s for the slow sinusoidal sway
const IDLE_ROT_AMP       = 0.055;   // ±~3.1° sway amplitude
const IDLE_LEVITATE_FREQ = 1.5;     // Hz of the vertical float
const IDLE_LEVITATE_AMP  = 0.08;    // ±0.08 units of vertical travel

// Mouse rotation influence at top: pointer.x maps to ±this many radians (~9°)
const POINTER_ROT_AMP    = 0.16;

// ─── Scroll-drive ─────────────────────────────────────────────────────────────
const SCROLL_ROTATION_DELTA = 0.18;   // ~10° total rotation at full scroll

// ─── isAtTopFactor transition band ────────────────────────────────────────────
// scrollY goes 0 → BLEND_BAND before isAtTopFactor fully drops to 0.
// Keeps the transition continuous; no hard cut at any single pixel.
const BLEND_BAND = 120;   // pixels — full blend happens inside first 120px

// ─── Camera parallax ──────────────────────────────────────────────────────────
const PARALLAX_X = 0.28;
const PARALLAX_Y = 0.14;


function BmwModel() {
  const { scene }  = useGLTF('/bmwm5.glb');
  const carRef     = useRef();
  const materialsRef = useRef([]);

  // Scroll-drive smoothing
  const smoothedProgress = useRef(0);

  // Reveal
  const revealProgress = useRef(0);
  const revealDone     = useRef(false);

  // Blended top-of-page factor (0 = fully scrolled, 1 = at top)
  // Smoothed every frame with damp so it never snaps.
  const topFactor = useRef(1);   // starts at 1 because page loads at top

  // ─── Mobile detection ─────────────────────────────────────────────────────
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // ─── Geometry ─────────────────────────────────────────────────────────────
  const scaleFactor = isMobile ? 0.6 : 1;
  const carScale    = 1.3 * scaleFactor;
  const startX      =  4  * scaleFactor;
  const startZ      =  2  * scaleFactor;
  const endX        = startX + (-40 * scaleFactor);
  const endZ        = startZ + (-25 * scaleFactor);
  const fixedAngle  = (Math.PI / 5) + Math.PI;

  // ─── Material — satin clearcoat ───────────────────────────────────────────
  // TASK 1: De-gloss.
  //   roughness 0.12 → 0.21  : scatters reflections over body panels naturally
  //   metalness 0.85 → 0.82  : still structurally metallic, not mirror-chrome
  //   envMapIntensity 3.2 → 2.0 : studio map lights without blowing out panels
  useLayoutEffect(() => {
    const mats = [];
    scene.traverse((child) => {
      if (child.isMesh) {
        const mat = new THREE.MeshStandardMaterial({
          color:           '#050505',
          roughness:       0.21,
          metalness:       0.82,
          envMapIntensity: 2.0,
          transparent:     true,
          opacity:         0,
        });
        child.material = mat;
        mats.push(mat);
      }
    });
    materialsRef.current = mats;
  }, [scene]);

  // ─── Render loop ───────────────────────────────────────────────────────────
  useFrame((state, delta) => {
    if (!carRef.current) return;

    const scrollY     = window.scrollY;
    const maxScroll   = document.body.scrollHeight - window.innerHeight;
    const rawProgress = maxScroll > 0 ? scrollY / maxScroll : 0;

    // ── Phase 1: Reveal (unchanged spring overshoot logic) ─────────────────
    if (!revealDone.current) {
      revealProgress.current = Math.min(
        revealProgress.current + delta / REVEAL_DURATION, 1
      );
      const t = revealProgress.current;

      let revealY;
      if (t < 0.85) {
        const e1 = 1 - Math.pow(1 - (t / 0.85), 3);
        revealY = THREE.MathUtils.lerp(REVEAL_Y_START, REVEAL_Y_OVERSHOOT, e1);
      } else {
        const e2 = 1 - Math.pow(1 - ((t - 0.85) / 0.15), 2);
        revealY = THREE.MathUtils.lerp(REVEAL_Y_OVERSHOOT, REVEAL_Y_REST, e2);
      }

      const opacity = Math.min((t / 0.85) * 1.15, 1);
      materialsRef.current.forEach(mat => { mat.opacity = opacity; });
      carRef.current.position.set(startX, revealY, startZ);
      carRef.current.rotation.y = fixedAngle;

      if (revealProgress.current >= 1) {
        materialsRef.current.forEach(mat => {
          mat.opacity = 1; mat.transparent = false; mat.needsUpdate = true;
        });
        revealDone.current = true;
      }
      return;
    }

    // ── Phase 2: Bi-directional state machine ──────────────────────────────

    // TASK 2 — Compute raw top-of-page factor every frame.
    // 1.0 when scrollY = 0, 0.0 when scrollY >= BLEND_BAND.
    // Clamped so it never goes below 0 or above 1.
    const rawTopFactor = Math.max(0, 1 - scrollY / BLEND_BAND);

    // TASK 3 — Smooth the factor with damp so state transitions never snap.
    // damp speed 5.0 means it reaches target in ~0.2 s — perceptibly fast
    // but not instant, eliminating any jerk at the threshold.
    topFactor.current = THREE.MathUtils.damp(
      topFactor.current, rawTopFactor, 5.0, delta
    );

    const tf = topFactor.current;   // alias — 1=top, 0=scrolled

    // Smooth scroll progress for the drive-off trajectory
    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current, rawProgress, 2.5, delta
    );
    const delayedProgress = Math.pow(smoothedProgress.current, 3);

    // ── Position ───────────────────────────────────────────────────────────
    const currentX = THREE.MathUtils.lerp(startX, endX, delayedProgress);
    const currentZ = THREE.MathUtils.lerp(startZ, endZ, delayedProgress);

    // TASK 2 — Levitation: active when tf > 0, fades as user scrolls away.
    // Uses state.clock (R3F clock, not local idleTime) so it continues
    // seamlessly when the user returns to the top.
    const elapsed     = state.clock.getElapsedTime();
    const levitation  = Math.sin(elapsed * IDLE_LEVITATE_FREQ) * IDLE_LEVITATE_AMP;
    const currentY    = REVEAL_Y_REST + levitation * tf;   // blend to 0 when scrolled

    carRef.current.position.set(currentX, currentY, currentZ);

    // ── Rotation ───────────────────────────────────────────────────────────
    // Three blended contributions, each weighted by tf or (1-tf):

    // 1. Idle sinusoidal sway — active at top (tf=1)
    const idleSway   = Math.sin(elapsed * IDLE_ROT_SPEED) * IDLE_ROT_AMP;
    const idleTarget = fixedAngle + idleSway * tf;

    // 2. Pointer rotation — maps pointer.x [-1,1] to ±POINTER_ROT_AMP
    //    Fully active at top, fades to 0 as user scrolls away.
    const pointerOffset = state.pointer.x * POINTER_ROT_AMP * tf;

    // 3. Scroll-driven travel rotation — active when scrolled (1-tf)
    const travelTarget = fixedAngle + SCROLL_ROTATION_DELTA * delayedProgress * (1 - tf);

    // Combine: blend between top-of-page orientation and scroll orientation
    const targetRotY = idleTarget + pointerOffset + (travelTarget - fixedAngle);

    carRef.current.rotation.y = THREE.MathUtils.damp(
      carRef.current.rotation.y, targetRotY, 5.0, delta
    );

    // ── Camera parallax ────────────────────────────────────────────────────
    // Parallax is fully active at top, fades by 60% when scrolled.
    // When scrolled, camera drifts back toward centre so the drive-off
    // trajectory doesn't fight a shifted viewport.
    const parallaxStrength = tf * PARALLAX_X + (1 - tf) * PARALLAX_X * 0.4;

    const targetCamX = state.pointer.x * parallaxStrength;
    const targetCamY = 2 + state.pointer.y * (parallaxStrength * 0.5);

    state.camera.position.x = THREE.MathUtils.damp(
      state.camera.position.x, targetCamX, 3.5, delta
    );
    state.camera.position.y = THREE.MathUtils.damp(
      state.camera.position.y, targetCamY, 3.5, delta
    );

    state.camera.lookAt(0, 0.3, 0);
  });

  return <primitive ref={carRef} object={scene} scale={carScale} />;
}


export default function Background3DShell() {
  return (
    <div id="canvas-container" className="fixed inset-0 z-0 w-full h-full pointer-events-none">
      <Canvas
        camera={{ position: [0, 2, 8], fov: 45 }}
        gl={{ antialias: true, toneMappingExposure: 1.75 }}
      >
        <Environment preset="studio" />
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={1.8} />
        <ContactShadows
          resolution={1024}
          scale={20}
          blur={4.5}
          opacity={0.32}
          far={10}
          color="#000000"
          position={[0, -1, 0]}
        />
        <React.Suspense fallback={null}>
          <BmwModel />
        </React.Suspense>
      </Canvas>
    </div>
  );
}

useGLTF.preload('/bmwm5.glb');
