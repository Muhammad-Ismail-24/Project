import React, { useRef, useLayoutEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, ContactShadows, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

// ─── Reveal animation constants ───────────────────────────────────────────────
// The car enters from below (Y offset) and fades in (opacity via material).
// All of this happens inside useFrame so it stays in the Three.js render loop
// and never touches React state — consistent with the existing scroll animation
// pattern that avoids re-renders deliberately.
const REVEAL_DURATION = 1.4;   // seconds until animation is complete
const REVEAL_Y_START  = -4.5;  // car starts this many units below its rest Y
const REVEAL_Y_REST   = -1;    // final rest Y (matches existing scroll logic)

function BmwModel() {
  const { scene } = useGLTF('/bmwm5.glb');
  const carRef = useRef();

  // Scroll progress — same pattern as before, no React state
  const smoothedProgress = useRef(0);

  // Reveal progress: 0 → 1 over REVEAL_DURATION seconds
  // We use a ref so it never triggers a re-render
  const revealProgress = useRef(0);
  const revealDone     = useRef(false);

  // We need a ref to the materials so we can drive opacity during reveal
  const materialsRef = useRef([]);

  useLayoutEffect(() => {
    const mats = [];
    scene.traverse((child) => {
      if (child.isMesh) {
        const mat = new THREE.MeshStandardMaterial({
          color:            '#050505',
          roughness:        0.15,
          metalness:        0.8,
          envMapIntensity:  2.5,
          transparent:      true,   // needed to animate opacity
          opacity:          0,      // start invisible
        });
        child.material = mat;
        mats.push(mat);
      }
    });
    materialsRef.current = mats;
  }, [scene]);

  useFrame((state, delta) => {
    if (!carRef.current) return;

    // ── 1. Reveal animation (runs once on load) ──────────────────────────────
    if (!revealDone.current) {
      revealProgress.current = Math.min(
        revealProgress.current + delta / REVEAL_DURATION,
        1
      );

      // Smooth easing: ease-out cubic  t → 1 - (1-t)³
      const t = revealProgress.current;
      const eased = 1 - Math.pow(1 - t, 3);

      // Drive Y position from start → rest during reveal
      const revealY = THREE.MathUtils.lerp(REVEAL_Y_START, REVEAL_Y_REST, eased);

      // Drive opacity 0 → 1 (slightly faster than position so it doesn't linger)
      const opacity = Math.min(eased * 1.3, 1);
      materialsRef.current.forEach(mat => { mat.opacity = opacity; });

      // Apply reveal Y — scroll logic will overwrite once reveal finishes
      carRef.current.position.y = revealY;

      if (revealProgress.current >= 1) {
        // Lock opacity at 1 permanently and disable transparent flag for perf
        materialsRef.current.forEach(mat => {
          mat.opacity     = 1;
          mat.transparent = false;
          mat.needsUpdate = true;
        });
        revealDone.current = true;
      }

      // During reveal, keep X/Z and rotation at their start values so the
      // entry feels clean — don't let scroll math fight the reveal
      const startX         = THREE.MathUtils.lerp(4, -15, 0);
      const startZ         = THREE.MathUtils.lerp(2, -2,  0);
      const startRotationY = (Math.PI / 5) + Math.PI;
      carRef.current.position.x  = startX;
      carRef.current.position.z  = startZ;
      carRef.current.rotation.y  = startRotationY;
      return;
    }

    // ── 2. Scroll-driven animation (existing logic, untouched) ───────────────
    const scrollY    = window.scrollY;
    const maxScroll  = document.body.scrollHeight - window.innerHeight;
    const rawProgress = maxScroll > 0 ? scrollY / maxScroll : 0;

    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current,
      rawProgress,
      2.5,
      delta
    );

    const currentX         = THREE.MathUtils.lerp(4,  -15, smoothedProgress.current);
    const currentZ         = THREE.MathUtils.lerp(2,   -2, smoothedProgress.current);
    const startAngle       = (Math.PI / 5)   + Math.PI;
    const endAngle         = (Math.PI / 1.5) + Math.PI;
    const currentRotationY = THREE.MathUtils.lerp(startAngle, endAngle, smoothedProgress.current);

    carRef.current.position.set(currentX, REVEAL_Y_REST, currentZ);
    carRef.current.rotation.y = currentRotationY;
  });

  return (
    <primitive
      ref={carRef}
      object={scene}
      scale={1.3}
    />
  );
}

export default function Background3DShell() {
  return (
    <div
      id="canvas-container"
      className="fixed inset-0 z-0 w-full h-full pointer-events-none"
    >
      <Canvas
        camera={{ position: [0, 2, 8], fov: 45 }}
        gl={{ antialias: true, toneMappingExposure: 1.2 }}
      >
        <Environment preset="city" />
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 5]} intensity={1.5} />
        <ContactShadows
          resolution={1024}
          scale={20}
          blur={2.5}
          opacity={0.6}
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
