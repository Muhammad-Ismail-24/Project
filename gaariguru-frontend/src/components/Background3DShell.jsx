/*
  Background3DShell.jsx
  Automotive 3D landing hero scene tracking.
  Provides premium, natural clearcoat reflections, seamless bi-directional state blending,
  and global mouse tracking to bypass pointer-events-none.
*/
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
const IDLE_ROT_SPEED     = 0.55;    // rad/s for the slow sinusoidal sway
const IDLE_ROT_AMP       = 0.055;   // ±~3.1° sway amplitude
const IDLE_LEVITATE_FREQ = 1.5;     // Hz of the vertical float
const IDLE_LEVITATE_AMP  = 0.08;    // ±0.08 units of vertical travel

// Mouse rotation influence at top: pointer.x maps to ±this many radians (~11.5°)
const POINTER_ROT_AMP    = 0.20;

// ─── Scroll-drive ─────────────────────────────────────────────────────────────
const SCROLL_ROTATION_DELTA = 0.18;   // ~10° total rotation at full scroll

// ─── isAtTopFactor transition band ────────────────────────────────────────────
const BLEND_BAND = 150;   // pixels — full blend happens inside first 150px

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
  const topFactor = useRef(1);

  // ─── Mobile detection ─────────────────────────────────────────────────────
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // ─── Global Mouse Tracker (Bypasses pointer-events-none) ───────────────
  const globalMouse = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e) => {
      // Normalize to match Three.js coordinate system (-1 to +1)
      globalMouse.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      globalMouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // ─── Geometry ─────────────────────────────────────────────────────────────
  const scaleFactor = isMobile ? 0.6 : 1;
  const carScale    = 1.3 * scaleFactor;
  const startX      =  4  * scaleFactor;
  const startZ      =  2  * scaleFactor;
  const endX        = startX + (-40 * scaleFactor);
  const endZ        = startZ + (-25 * scaleFactor);
  const fixedAngle  = (Math.PI / 5) + Math.PI;

  // ─── Material — natural satin clearcoat ────────────────────────────────────
  useLayoutEffect(() => {
    const mats = [];
    scene.traverse((child) => {
      if (child.isMesh) {
        const mat = new THREE.MeshStandardMaterial({
          color:           '#080808',
          roughness:       0.28,      // Increased to break down the plasticky gloss reflections
          metalness:       0.85,      // Stays structurally heavyweight metal
          envMapIntensity: 1.4,       // Balanced studio reflection intensity
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

    // ── Phase 1: Reveal ────────────────────────────────────────────────────
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

    // Compute raw top factor (1.0 = top of page, 0.0 = scrolled down)
    const rawTopFactor = Math.max(0, 1 - scrollY / BLEND_BAND);

    // Smooth state transitions to eliminate jerking
    topFactor.current = THREE.MathUtils.damp(
      topFactor.current, rawTopFactor, 4.0, delta
    );

    const tf = topFactor.current; // 1 = at top, 0 = scrolled down

    // Smooth the absolute scrolling progress tracking
    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current, rawProgress, 2.5, delta
    );
    const delayedProgress = Math.pow(smoothedProgress.current, 3);

    // ── Position Blending ──────────────────────────────────────────────────
    const targetX = THREE.MathUtils.lerp(startX, endX, delayedProgress);
    const targetZ = THREE.MathUtils.lerp(startZ, endZ, delayedProgress);

    // Levitation recalculates smoothly from state.clock whenever tf > 0
    const elapsed    = state.clock.getElapsedTime();
    const levitation = Math.sin(elapsed * IDLE_LEVITATE_FREQ) * IDLE_LEVITATE_AMP;
    
    // Combine base trajectory tracking with the animated levitation factor
    const finalY = REVEAL_Y_REST + (levitation * tf);

    carRef.current.position.set(targetX, finalY, targetZ);

    // ── Rotation Blending ──────────────────────────────────────────────────
    // Top-of-page interactive rotation target
    const idleSway     = Math.sin(elapsed * IDLE_ROT_SPEED) * IDLE_ROT_AMP;
    const pointerSway  = globalMouse.current.x * POINTER_ROT_AMP;
    const topStateRotY = fixedAngle + idleSway + pointerSway;

    // Scrolled driving trajectory target
    const scrollStateRotY = fixedAngle + (SCROLL_ROTATION_DELTA * delayedProgress);

    // Linearly interpolate between top interactive state and scroll drive state based on tf
    const finalTargetRotY = THREE.MathUtils.lerp(scrollStateRotY, topStateRotY, tf);

    carRef.current.rotation.y = THREE.MathUtils.damp(
      carRef.current.rotation.y, finalTargetRotY, 5.0, delta
    );

    // ── Camera Parallax ────────────────────────────────────────────────────
    const parallaxStrength = tf * PARALLAX_X + (1 - tf) * PARALLAX_X * 0.4;

    const targetCamX = globalMouse.current.x * parallaxStrength;
    const targetCamY = 2 + globalMouse.current.y * (parallaxStrength * 0.5);

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
        gl={{ antialias: true, toneMappingExposure: 1.5 }}
      >
        <Environment preset="studio" />
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={1.3} />
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