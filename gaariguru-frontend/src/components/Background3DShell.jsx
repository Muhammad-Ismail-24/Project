import React, { useRef, useLayoutEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, ContactShadows, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

const REVEAL_DURATION = 1.4;
const REVEAL_Y_START  = -4.5;
const REVEAL_Y_REST   = -1;

function BmwModel() {
  const { scene } = useGLTF('/bmwm5.glb');
  const carRef = useRef();
  const smoothedProgress = useRef(0);
  const revealProgress = useRef(0);
  const revealDone = useRef(false);
  const materialsRef = useRef([]);

  useLayoutEffect(() => {
    const mats = [];
    scene.traverse((child) => {
      if (child.isMesh) {
        const mat = new THREE.MeshStandardMaterial({
          color: '#050505',
          roughness: 0.15,
          metalness: 0.8,
          envMapIntensity: 2.5,
          transparent: true,
          opacity: 0,
        });
        child.material = mat;
        mats.push(mat);
      }
    });
    materialsRef.current = mats;
  }, [scene]);

  useFrame((state, delta) => {
    if (!carRef.current) return;

    // ── 1. Reveal Animation ──
    if (!revealDone.current) {
      revealProgress.current = Math.min(revealProgress.current + delta / REVEAL_DURATION, 1);
      const t = revealProgress.current;
      const eased = 1 - Math.pow(1 - t, 3);
      
      const revealY = THREE.MathUtils.lerp(REVEAL_Y_START, REVEAL_Y_REST, eased);
      const opacity = Math.min(eased * 1.3, 1);
      
      materialsRef.current.forEach(mat => { mat.opacity = opacity; });
      carRef.current.position.y = revealY;

      if (revealProgress.current >= 1) {
        materialsRef.current.forEach(mat => {
          mat.opacity = 1;
          mat.transparent = false;
          mat.needsUpdate = true;
        });
        revealDone.current = true;
      }

      carRef.current.position.x = 4;
      carRef.current.position.z = 2;
      carRef.current.rotation.y = (Math.PI / 5) + Math.PI;
      return;
    }

    // ── 2. Cinematic Drive-Off Trajectory (Ratio Fixed) ──
    const scrollY = window.scrollY;
    const maxScroll = document.body.scrollHeight - window.innerHeight;
    const rawProgress = maxScroll > 0 ? scrollY / maxScroll : 0;

    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current,
      rawProgress,
      2.5,
      delta
    );

    // FIXED: Maintained the exact 5:8 ratio for Z:X travel to prevent sideways drifting.
    // Original good ratio was X: 4 to -12 (diff -16), Z: 2 to -8 (diff -10).
    // Scaled by 2.5x to drive off screen -> X diff: -40, Z diff: -25.
    // New Targets -> X: 4 - 40 = -36 | Z: 2 - 25 = -23
    const currentX = THREE.MathUtils.lerp(4, -36, smoothedProgress.current);
    const currentZ = THREE.MathUtils.lerp(2, -23, smoothedProgress.current);
    
    // Locked angle for perfectly straight reversing
    const fixedAngle = (Math.PI / 5) + Math.PI;

    carRef.current.position.set(currentX, REVEAL_Y_REST, currentZ);
    carRef.current.rotation.y = fixedAngle;
  });

  return <primitive ref={carRef} object={scene} scale={1.3} />;
}

export default function Background3DShell() {
  return (
    <div id="canvas-container" className="fixed inset-0 z-0 w-full h-full pointer-events-none">
      <Canvas camera={{ position: [0, 2, 8], fov: 45 }} gl={{ antialias: true, toneMappingExposure: 1.2 }}>
        <Environment preset="city" />
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 5]} intensity={1.5} />
        <ContactShadows resolution={1024} scale={20} blur={2.5} opacity={0.6} far={10} color="#000000" position={[0, -1, 0]} />
        <React.Suspense fallback={null}>
          <BmwModel />
        </React.Suspense>
      </Canvas>
    </div>
  );
}

useGLTF.preload('/bmwm5.glb');