import React, { useRef, useLayoutEffect, useState, useEffect } from 'react';
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

  // ─── Mobile Detection ───
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // ─── Mathematical Scale Factor ───
  // Shrink the car and its trajectory by 40% on mobile to fit the narrow screen
  const scaleFactor = isMobile ? 0.6 : 1; 
  const carScale = 1.3 * scaleFactor;
  
  // Starting positions
  const startX = 4 * scaleFactor;
  const startZ = 2 * scaleFactor;
  
  // Deltas (Maintains the exact 25/40 ratio to prevent drifting)
  const deltaX = -40 * scaleFactor;
  const deltaZ = -25 * scaleFactor;
  
  // End positions
  const endX = startX + deltaX;
  const endZ = startZ + deltaZ;

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

    // Locked angle for perfectly straight reversing
    const fixedAngle = (Math.PI / 5) + Math.PI;

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

      carRef.current.position.x = startX;
      carRef.current.position.z = startZ;
      carRef.current.rotation.y = fixedAngle;
      return;
    }

    // ── 2. Cinematic Drive-Off Trajectory ──
    const scrollY = window.scrollY;
    const maxScroll = document.body.scrollHeight - window.innerHeight;
    const rawProgress = maxScroll > 0 ? scrollY / maxScroll : 0;

    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current,
      rawProgress,
      2.5,
      delta
    );

    const delayedProgress = Math.pow(smoothedProgress.current, 3);

    // Dynamic endpoints based on screen size
    const currentX = THREE.MathUtils.lerp(startX, endX, delayedProgress);
    const currentZ = THREE.MathUtils.lerp(startZ, endZ, delayedProgress);

    carRef.current.position.set(currentX, REVEAL_Y_REST, currentZ);
    carRef.current.rotation.y = fixedAngle;
  });

  return <primitive ref={carRef} object={scene} scale={carScale} />;
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