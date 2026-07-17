/*
  Background3DShell.jsx
  Automotive 3D landing hero scene tracking.
  Provides premium clearcoat reflections, bi-directional scroll blending,
  placeholder-locked horizontal turntable drag, and pure horizontal trajectory.
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

// ─── Scalings ──────────────────────────────────────────────────────────────────
const BASE_SCALE = 1.15; 

// ─── Top-of-page idle state ────────────────────────────────────────────────────
const IDLE_ROT_SPEED     = 0.55;    // rad/s for the slow sinusoidal sway
const IDLE_ROT_AMP       = 0.055;   // ±~3.1° sway amplitude
const IDLE_LEVITATE_FREQ = 1.5;     // Hz of the vertical float
const IDLE_LEVITATE_AMP  = 0.08;    // ±0.08 units of vertical travel
const POINTER_ROT_AMP    = 0.20;

// ─── Angles ───────────────────────────────────────────────────────────────────
const START_ANGLE       = (Math.PI / 5) + Math.PI; // 216 deg (front-left resting angle)
const TARGET_LEFT_ANGLE = Math.PI * 1.5;           // 270 deg (pure profile left)

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

  // ─── Global Mouse & Horizontal Drag Tracker ─────────────────────────────
  const globalMouse  = useRef({ x: 0, y: 0 });
  const dragOffset   = useRef(0); 
  const isDragging   = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const handleDown = (e) => {
      if (window.scrollY > 20) return;

      if (e.button !== 0 && e.type === 'mousedown') return;
      if (e.target.closest('button, a, input, select, textarea, [role="button"]')) return;

      isDragging.current = true;
      lastMousePos.current = {
        x: e.touches ? e.touches[0].clientX : e.clientX,
        y: e.touches ? e.touches[0].clientY : e.clientY
      };
    };

    const handleMove = (e) => {
      const currentX = e.touches ? e.touches[0].clientX : e.clientX;
      const currentY = e.touches ? e.touches[0].clientY : e.clientY;

      globalMouse.current.x = (currentX / window.innerWidth) * 2 - 1;
      globalMouse.current.y = -(currentY / window.innerHeight) * 2 + 1;

      if (isDragging.current) {
        if (window.scrollY > 20) {
          isDragging.current = false;
          return;
        }

        if (e.type === 'mousemove' && e.buttons !== 1) {
          isDragging.current = false;
          return;
        }

        if (window.getSelection) {
          window.getSelection().removeAllRanges();
        }

        const deltaX = currentX - lastMousePos.current.x;
        dragOffset.current += deltaX * 0.012; 
        
        lastMousePos.current = { x: currentX, y: currentY };
      }
    };

    const handleUp = () => {
      isDragging.current = false;
    };

    window.addEventListener('mousedown', handleDown);
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    window.addEventListener('touchstart', handleDown);
    window.addEventListener('touchmove', handleMove);
    window.addEventListener('touchend', handleUp);

    return () => {
      window.removeEventListener('mousedown', handleDown);
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
      window.removeEventListener('touchstart', handleDown);
      window.removeEventListener('touchmove', handleMove);
      window.removeEventListener('touchend', handleUp);
    };
  }, []);

  // ─── Geometry ─────────────────────────────────────────────────────────────
  const scaleFactor = isMobile ? 0.6 : 1;
  const carScale    = BASE_SCALE * scaleFactor;
  
  // Adjusted to create a perfect horizontal rail (endZ matches startZ perfectly)
  const startX      =  3.5 * scaleFactor;
  const startZ      =  0.5 * scaleFactor; 
  const endX        = -10  * scaleFactor; // Enough to clear screen, prevents perspective drop
  const endZ        =  0.5 * scaleFactor; 

  // ─── Material — real automotive clearcoat paint ────────────────────────────
  useLayoutEffect(() => {
    const mats = [];
    scene.traverse((child) => {
      if (child.isMesh) {
        const mat = new THREE.MeshPhysicalMaterial({
          color:              '#080808',  
          roughness:          0.42,       
          metalness:          0.88,       
          envMapIntensity:    0.85,       
          clearcoat:          0.95,       
          clearcoatRoughness: 0.12,       
          transparent:        true,
          opacity:            0,
        });
        child.material = mat;
        child.castShadow    = true;
        child.receiveShadow = true;
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
      carRef.current.rotation.y = START_ANGLE;
      carRef.current.rotation.x = 0;

      if (revealProgress.current >= 1) {
        materialsRef.current.forEach(mat => {
          mat.opacity = 1; mat.transparent = false; mat.needsUpdate = true;
        });
        revealDone.current = true;
      }
      return;
    }

    // ── Phase 2: Core State Machine ─────────────────────────────────────────
    const rawTopFactor = Math.max(0, 1 - scrollY / BLEND_BAND);
    topFactor.current = THREE.MathUtils.damp(
      topFactor.current, rawTopFactor, 4.0, delta
    );
    const tf = topFactor.current; 

    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current, rawProgress, 2.5, delta
    );
    
    // Core timing curve
    const delayedProgress = Math.pow(smoothedProgress.current, 1.5); 

    // 1. BASE SCROLL PATH (Unbreakable straight horizontal rail)
    const targetX = THREE.MathUtils.lerp(startX, endX, delayedProgress);
    const targetZ = THREE.MathUtils.lerp(startZ, endZ, delayedProgress);
    const baseScrollAngle = THREE.MathUtils.lerp(START_ANGLE, TARGET_LEFT_ANGLE, delayedProgress);

    // 2. Y-AXIS LEVITATION
    const elapsed    = state.clock.getElapsedTime();
    const levitation = Math.sin(elapsed * IDLE_LEVITATE_FREQ) * IDLE_LEVITATE_AMP;
    const finalY = REVEAL_Y_REST + (levitation * tf);

    carRef.current.position.set(targetX, finalY, targetZ);

    // 3. SHORTEST PATH & INTERACTIVE ROTATION
    const PI2 = Math.PI * 2;
    const cycles = Math.round(dragOffset.current / PI2);
    const baseOffset = cycles * PI2;

    const idleSway    = Math.sin(elapsed * IDLE_ROT_SPEED) * IDLE_ROT_AMP;
    const pointerSway = globalMouse.current.x * POINTER_ROT_AMP;
    
    // We strictly isolate the interactive modifiers and fade them out based on `tf`.
    // This mathematically prevents the parabolic dual-lerp clash.
    const dragRemainder = dragOffset.current - baseOffset;
    const interactiveOffset = (idleSway + pointerSway + dragRemainder) * tf;

    carRef.current.rotation.y = THREE.MathUtils.damp(
      carRef.current.rotation.y, 
      baseOffset + baseScrollAngle + interactiveOffset, 
      5.0, 
      delta
    );
    carRef.current.rotation.x = 0;

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
        gl={{
          antialias: true,
          toneMappingExposure: 0.72,
        }}
      >
        <Environment preset="studio" />
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={0.5} />
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