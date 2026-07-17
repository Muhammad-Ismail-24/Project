import React, { useRef, useLayoutEffect, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, ContactShadows, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

// ─── Reveal constants ──────────────────────────────────────────────────────────
const REVEAL_DURATION    = 1.6;    // slightly longer so the spring settle has room
const REVEAL_Y_START     = -4.5;
const REVEAL_Y_REST      = -1;
// Spring overshoot: car rises ABOVE rest, then settles back — like suspension bounce
const REVEAL_Y_OVERSHOOT = REVEAL_Y_REST + 0.22;   // 0.22 units above final rest

// ─── Idle showroom rotation ────────────────────────────────────────────────────
// After reveal, car slowly sways ±IDLE_AMPLITUDE radians — stops on first scroll
const IDLE_SPEED     = 0.55;    // rad/s — slow, luxurious
const IDLE_AMPLITUDE = 0.055;   // ±~3.1 degrees

// ─── Scroll-driven rotation delta ─────────────────────────────────────────────
// Car rotates slightly to face its direction of travel as it drives off
const SCROLL_ROTATION_DELTA = 0.18;   // ~10 degrees at full scroll

// ─── Mouse parallax ───────────────────────────────────────────────────────────
const PARALLAX_STRENGTH = 0.28;   // camera shifts ±this many units


function BmwModel() {
  const { scene } = useGLTF('/bmwm5.glb');
  const carRef = useRef();

  // Scroll smoothing
  const smoothedProgress = useRef(0);

  // Reveal state
  const revealProgress = useRef(0);
  const revealDone     = useRef(false);

  // Idle rotation clock (accumulated delta after reveal)
  const idleTime = useRef(0);

  // Ends idle phase on first scroll
  const hasScrolled = useRef(false);

  const materialsRef = useRef([]);

  // ─── Mobile detection ─────────────────────────────────────────────────────
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // ─── Geometry (scale-adjusted, unchanged ratios) ───────────────────────────
  const scaleFactor = isMobile ? 0.6 : 1;
  const carScale    = 1.3 * scaleFactor;

  const startX = 4  * scaleFactor;
  const startZ = 2  * scaleFactor;
  const endX   = startX + (-40 * scaleFactor);
  const endZ   = startZ + (-25 * scaleFactor);

  // Base heading — same as original fixedAngle
  const fixedAngle = (Math.PI / 5) + Math.PI;

  // ─── Material setup ────────────────────────────────────────────────────────
  // FIX 4 partial — material params: lower roughness + higher metalness/envMap
  // so the "studio" environment (fix 6) reflects cleanly in the black paint.
  useLayoutEffect(() => {
    const mats = [];
    scene.traverse((child) => {
      if (child.isMesh) {
        const mat = new THREE.MeshStandardMaterial({
          color:           '#050505',
          roughness:       0.12,   // 0.15 → 0.12: slightly more reflective
          metalness:       0.85,   // 0.80 → 0.85: deeper, richer black
          envMapIntensity: 3.2,    // 2.5 → 3.2: studio preset captures better
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

    if (scrollY > 2) hasScrolled.current = true;

    // ── Phase 1: Reveal with spring overshoot (FIX 3) ─────────────────────
    if (!revealDone.current) {
      revealProgress.current = Math.min(
        revealProgress.current + delta / REVEAL_DURATION,
        1
      );
      const t = revealProgress.current;

      // Two-phase Y:
      //   0 → 0.85 : ease-out cubic rising to OVERSHOOT
      //   0.85 → 1 : ease-out quad settling back to REST
      let revealY;
      if (t < 0.85) {
        const t1 = t / 0.85;
        const e1 = 1 - Math.pow(1 - t1, 3);
        revealY = THREE.MathUtils.lerp(REVEAL_Y_START, REVEAL_Y_OVERSHOOT, e1);
      } else {
        const t2 = (t - 0.85) / 0.15;
        const e2 = 1 - Math.pow(1 - t2, 2);
        revealY = THREE.MathUtils.lerp(REVEAL_Y_OVERSHOOT, REVEAL_Y_REST, e2);
      }

      // Opacity reaches 1 by t≈0.74 so the car is fully visible before spring
      const opacity = Math.min((t / 0.85) * 1.15, 1);
      materialsRef.current.forEach(mat => { mat.opacity = opacity; });

      carRef.current.position.set(startX, revealY, startZ);
      carRef.current.rotation.y = fixedAngle;

      if (revealProgress.current >= 1) {
        materialsRef.current.forEach(mat => {
          mat.opacity     = 1;
          mat.transparent = false;
          mat.needsUpdate = true;
        });
        revealDone.current = true;
      }
      return;
    }

    // ── Phase 2: Post-reveal — idle sway and/or scroll drive-off ──────────

    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current,
      rawProgress,
      2.5,
      delta
    );

    const delayedProgress = Math.pow(smoothedProgress.current, 3);

    // Position (unchanged trajectory)
    const currentX = THREE.MathUtils.lerp(startX, endX, delayedProgress);
    const currentZ = THREE.MathUtils.lerp(startZ, endZ, delayedProgress);
    carRef.current.position.set(currentX, REVEAL_Y_REST, currentZ);

    // ── Rotation logic ─────────────────────────────────────────────────────
    if (!hasScrolled.current) {
      // FIX 1 — Idle showroom sway: sinusoidal ±3° around fixedAngle
      idleTime.current += delta;
      const sway = Math.sin(idleTime.current * IDLE_SPEED) * IDLE_AMPLITUDE;
      carRef.current.rotation.y = fixedAngle + sway;
    } else {
      // FIX 2 — Scroll-driven rotation: car faces direction of travel
      const travelAngle = fixedAngle + SCROLL_ROTATION_DELTA * delayedProgress;
      carRef.current.rotation.y = THREE.MathUtils.damp(
        carRef.current.rotation.y,
        travelAngle,
        4.0,
        delta
      );
    }

    // ── FIX 7 — Mouse parallax ─────────────────────────────────────────────
    // state.mouse is normalised [-1,1]. Damp so camera lags behind cursor.
    const targetCamX = state.mouse.x * PARALLAX_STRENGTH;
    const targetCamY = 2 + state.mouse.y * (PARALLAX_STRENGTH * 0.5);

    state.camera.position.x = THREE.MathUtils.damp(
      state.camera.position.x, targetCamX, 3.5, delta
    );
    state.camera.position.y = THREE.MathUtils.damp(
      state.camera.position.y, targetCamY, 3.5, delta
    );

    // Always point at scene centre so parallax shifts perspective, not framing
    state.camera.lookAt(0, 0.3, 0);
  });

  return <primitive ref={carRef} object={scene} scale={carScale} />;
}


export default function Background3DShell() {
  return (
    <div id="canvas-container" className="fixed inset-0 z-0 w-full h-full pointer-events-none">
      <Canvas
        camera={{ position: [0, 2, 8], fov: 45 }}
        gl={{
          antialias:           true,
          // FIX 4 — Exposure: 1.2 → 1.75. Black paint becomes more dramatic;
          // reflective highlights pop against the grey background.
          toneMappingExposure: 1.75,
        }}
      >
        {/*
          FIX 6 — Environment preset: "city" → "studio"
          City had orange/blue light pollution visible in the paint reflections.
          Studio gives clean, neutral metallic reflections — correct for black
          car on grey background, looks like actual product photography.
        */}
        <Environment preset="studio" />

        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={1.8} />

        {/*
          FIX 5 — Contact shadow: softer + lighter.
          blur 2.5 → 4.5, opacity 0.6 → 0.32.
          Real showroom floors have very diffused ground shadows, not sharp ones.
        */}
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
