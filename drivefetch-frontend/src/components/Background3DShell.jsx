/*
  Background3DShell.jsx
  Automotive 3D landing hero scene tracking.
  Provides premium clearcoat reflections, bi-directional scroll blending,
  placeholder-locked horizontal turntable drag, pure horizontal trajectory,
  and safe, non-destructive wheel rotation.

  CSP-SAFE: Self-hosted Draco decoder at /draco/ (no gstatic.com, no remote HDR).
  - Environment preset="studio" removed: fetches from raw.githack.com (CSP blocked).
  - DRACOLoader pointed at /public/draco/ so it loads from 'self'.
  - vercel.json: script-src 'wasm-unsafe-eval', connect-src blob:, worker-src blob:
  - vercel.json: /draco/:file* pass-through rewrite must come before the SPA catch-all.
  Setup (run once): 
    mkdir -p public/draco
    cp node_modules/three/examples/jsm/libs/draco/draco_wasm_wrapper.js public/draco/
    cp node_modules/three/examples/jsm/libs/draco/draco_decoder.wasm    public/draco/
*/
import React, { useRef, useLayoutEffect, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { ContactShadows, Environment, Lightformer } from '@react-three/drei';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader';
import bmwModelUrl from '../assets/bmwm5.glb?url';

// ─── GLTF loader with self-hosted Draco decoder ────────────────────────────────
// DRACOLoader points at /draco/ (your public folder) — served from 'self',
// so no gstatic.com connect-src violation. setDecoderConfig removed (deprecated r193+).
function useGLTFNoDraco(url) {
  const [scene, setScene] = useState(null);
  useEffect(() => {
    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath('/draco/');   // serves from 'self' — CSP-safe

    const loader = new GLTFLoader();
    loader.setDRACOLoader(dracoLoader);

    loader.load(
      url,
      (gltf) => {
        dracoLoader.dispose();
        setScene(gltf.scene);
      },
      undefined,
      (err) => console.error('[Background3DShell] GLTF load error:', err),
    );

    return () => { dracoLoader.dispose(); };
  }, [url]);
  return scene;
}

// ─── CSP-safe procedural environment (replaces <Environment preset="studio" />) ─
// drei's Environment preset fetches an HDR from raw.githack.com — CSP blocked.
// Environment with children uses Lightformers to generate an internal envMap
// entirely in-GPU with zero network requests, restoring the metalness/clearcoat
// reflections that MeshPhysicalMaterial requires to look correct.
// resolution={256} keeps GPU memory low while giving sharp enough reflections
// on a smooth automotive body.
function CSPStudioEnvironment() {
  return (
    <>
      {/* Fallback scene lights — render even if WebGL envMap fails */}
      <ambientLight intensity={0.4} />
      <directionalLight position={[10, 10, 5]} intensity={0.5} />

      {/* Procedural envMap — no HDR fetch, no external URLs */}
      <Environment resolution={256}>
        {/* Main overhead softbox — creates the long highlight streak on the hood */}
        <Lightformer
          form="rect"
          intensity={4}
          position={[0, 10, -3]}
          scale={[10, 5, 1]}
          target={[0, 0, 0]}
        />
        {/* Left fill — cool side light, softens shadow side of body */}
        <Lightformer
          form="rect"
          intensity={2}
          position={[-5, 2, 0]}
          scale={[5, 10, 1]}
          target={[0, 0, 0]}
        />
        {/* Right rim — hot edge highlight on the roofline and rear quarter */}
        <Lightformer
          form="rect"
          intensity={3}
          position={[5, 5, 5]}
          scale={[5, 10, 1]}
          target={[0, 0, 0]}
        />
        {/* Ground bounce — warm undercar glow reflected in sills */}
        <Lightformer
          form="circle"
          intensity={1}
          position={[0, -5, 0]}
          scale={[10, 10, 1]}
          target={[0, 0, 0]}
        />
      </Environment>
    </>
  );
}
const REVEAL_DURATION    = 1.6;
const REVEAL_Y_START     = -4.5;
const REVEAL_Y_REST      = -1;
const REVEAL_Y_OVERSHOOT = REVEAL_Y_REST + 0.22;

// ─── Scalings ──────────────────────────────────────────────────────────────────
const BASE_SCALE = 1.15; 

// ─── Top-of-page idle state ────────────────────────────────────────────────────
const IDLE_ROT_SPEED     = 0.55;    
const IDLE_ROT_AMP       = 0.055;   
const IDLE_LEVITATE_FREQ = 1.5;     
const IDLE_LEVITATE_AMP  = 0.08;    
const POINTER_ROT_AMP    = 0.20;

// ─── Angles ───────────────────────────────────────────────────────────────────
const START_ANGLE       = (Math.PI / 5) + Math.PI; 
const TARGET_LEFT_ANGLE = Math.PI + 0.12;          

// ─── isAtTopFactor transition band ────────────────────────────────────────────
const BLEND_BAND = 150;   

// ─── Camera parallax ──────────────────────────────────────────────────────────
const PARALLAX_X = 0.28;
const PARALLAX_Y = 0.14;


function BmwModel() {
  const scene      = useGLTFNoDraco(bmwModelUrl);
  const carRef     = useRef();
  const materialsRef = useRef([]);

  const smoothedProgress = useRef(0);
  const revealProgress = useRef(0);
  const revealDone     = useRef(false);
  const topFactor = useRef(1);

  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

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

  const scaleFactor = isMobile ? 0.6 : 1;
  const carScale    = BASE_SCALE * scaleFactor;
  
  const startX      =  3.5 * scaleFactor;
  const startZ      =  0.5 * scaleFactor; 
  const endX        = -20  * scaleFactor; 
  const endZ        =  0.5 * scaleFactor; 

  useLayoutEffect(() => {
    // scene is null on first render while loading — skip material setup until ready
    if (!scene) return;
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

  useFrame((state, delta) => {
    if (!carRef.current) return;

    const scrollY     = window.scrollY;
    const maxScroll   = document.body.scrollHeight - window.innerHeight;
    const rawProgress = maxScroll > 0 ? scrollY / maxScroll : 0;

    if (!revealDone.current) {
      revealProgress.current = Math.min(revealProgress.current + delta / REVEAL_DURATION, 1);
      const t = revealProgress.current;
      let revealY;
      if (t < 0.85) {
        revealY = THREE.MathUtils.lerp(REVEAL_Y_START, REVEAL_Y_OVERSHOOT, 1 - Math.pow(1 - (t / 0.85), 3));
      } else {
        revealY = THREE.MathUtils.lerp(REVEAL_Y_OVERSHOOT, REVEAL_Y_REST, 1 - Math.pow(1 - ((t - 0.85) / 0.15), 2));
      }
      const opacity = Math.min((t / 0.85) * 1.15, 1);
      materialsRef.current.forEach(mat => { mat.opacity = opacity; });
      carRef.current.position.set(startX, revealY, startZ);
      carRef.current.rotation.y = START_ANGLE;
      carRef.current.rotation.x = 0;
      if (revealProgress.current >= 1) {
        materialsRef.current.forEach(mat => { mat.opacity = 1; mat.transparent = false; mat.needsUpdate = true; });
        revealDone.current = true;
      }
      return;
    }

    const rawTopFactor = Math.max(0, 1 - scrollY / BLEND_BAND);
    topFactor.current = THREE.MathUtils.damp(topFactor.current, rawTopFactor, 4.0, delta);
    const tf = topFactor.current; 

    smoothedProgress.current = THREE.MathUtils.damp(smoothedProgress.current, rawProgress, 2.5, delta);
    const delayedProgress = Math.pow(smoothedProgress.current, 1.5); 

    const targetX = THREE.MathUtils.lerp(startX, endX, delayedProgress);
    const targetZ = THREE.MathUtils.lerp(startZ, endZ, delayedProgress);
    const baseScrollAngle = THREE.MathUtils.lerp(START_ANGLE, TARGET_LEFT_ANGLE, delayedProgress);

    const elapsed    = state.clock.getElapsedTime();
    const levitation = Math.sin(elapsed * IDLE_LEVITATE_FREQ) * IDLE_LEVITATE_AMP;
    const finalY = REVEAL_Y_REST + (levitation * tf);

    carRef.current.position.set(targetX, finalY, targetZ);

    const PI2 = Math.PI * 2;
    const cycles = Math.round(dragOffset.current / PI2);
    const baseOffset = cycles * PI2;
    const idleSway    = Math.sin(elapsed * IDLE_ROT_SPEED) * IDLE_ROT_AMP;
    const pointerSway = globalMouse.current.x * POINTER_ROT_AMP;
    const dragRemainder = dragOffset.current - baseOffset;
    const interactiveOffset = (idleSway + pointerSway + dragRemainder) * tf;

    carRef.current.rotation.y = THREE.MathUtils.damp(
      carRef.current.rotation.y, 
      baseOffset + baseScrollAngle + interactiveOffset, 
      5.0, 
      delta
    );
    carRef.current.rotation.x = 0;

    // 4. PARALLAX
    const parallaxStrength = tf * PARALLAX_X;  
    const targetCamX = globalMouse.current.x * parallaxStrength;
    const targetCamY = 2 + globalMouse.current.y * (parallaxStrength * 0.5);

    state.camera.position.x = THREE.MathUtils.damp(state.camera.position.x, targetCamX, 3.5, delta);
    state.camera.position.y = THREE.MathUtils.damp(state.camera.position.y, targetCamY, 3.5, delta);
    state.camera.lookAt(0, 0.3, 0);
  });

  // Guard is in the render return — all hooks above always run unconditionally
  if (!scene) return null;
  return <primitive ref={carRef} object={scene} scale={carScale} />;
}

export default function Background3DShell() {
  return (
    <div id="canvas-container" className="fixed inset-0 z-0 w-full h-full pointer-events-none">
      <Canvas
        camera={{ position: [0, 2, 8], fov: 45 }}
        gl={{ antialias: true, toneMappingExposure: 0.72 }}
      >
        <CSPStudioEnvironment />
        <ContactShadows resolution={1024} scale={20} blur={4.5} opacity={0.32} far={10} color="#000000" position={[0, -1, 0]} />
        <React.Suspense fallback={null}>
          <BmwModel />
        </React.Suspense>
      </Canvas>
    </div>
  );
}

// NOTE: useGLTF.preload removed — we use a manual loader (useGLTFNoDraco)
// that doesn't go through drei's preload registry.