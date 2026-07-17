/*
  Background3DShell.jsx
  Final optimized version including drag rotation, natural lighting, and scroll trajectory.
*/
import React, { useRef, useLayoutEffect, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, ContactShadows, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

const REVEAL_DURATION = 1.6;
const REVEAL_Y_START = -4.5;
const REVEAL_Y_REST = -1;
const REVEAL_Y_OVERSHOOT = -0.78;
const BASE_SCALE = 0.95; 

function BmwModel() {
  const { scene } = useGLTF('/bmwm5.glb');
  const carRef = useRef();
  const materialsRef = useRef([]);
  const smoothedProgress = useRef(0);
  const revealProgress = useRef(0);
  const revealDone = useRef(false);
  const topFactor = useRef(1);
  const globalMouse = useRef({ x: 0, y: 0 });
  const dragOffset = useRef(0);
  const isDragging = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const handleMove = (e) => {
      const x = e.touches ? e.touches[0].clientX : e.clientX;
      const y = e.touches ? e.touches[0].clientY : e.clientY;
      globalMouse.current = { x: (x / window.innerWidth) * 2 - 1, y: -(y / window.innerHeight) * 2 + 1 };
      if (isDragging.current && window.scrollY <= 20) {
        dragOffset.current += (x - lastMousePos.current.x) * 0.012;
        lastMousePos.current = { x, y };
      }
    };
    const handleDown = (e) => {
      if (window.scrollY > 20 || e.button !== 0 || e.target.closest('button, a, input')) return;
      isDragging.current = true;
      lastMousePos.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('mousedown', handleDown);
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', () => (isDragging.current = false));
    return () => { window.removeEventListener('mousedown', handleDown); window.removeEventListener('mousemove', handleMove); };
  }, []);

  useLayoutEffect(() => {
    scene.traverse((child) => {
      if (child.isMesh) {
        child.material = new THREE.MeshStandardMaterial({ color: '#050505', roughness: 0.35, metalness: 0.85, envMapIntensity: 1.0, transparent: true, opacity: 0 });
        materialsRef.current.push(child.material);
      }
    });
  }, [scene]);

  useFrame((state, delta) => {
    if (!carRef.current) return;
    const scrollY = window.scrollY;
    const rawProgress = Math.min(scrollY / (document.body.scrollHeight - window.innerHeight), 1);
    
    if (!revealDone.current) {
      revealProgress.current = Math.min(revealProgress.current + delta / REVEAL_DURATION, 1);
      const t = revealProgress.current;
      const y = t < 0.85 ? THREE.MathUtils.lerp(REVEAL_Y_START, REVEAL_Y_OVERSHOOT, 1 - Math.pow(1 - (t / 0.85), 3)) : THREE.MathUtils.lerp(REVEAL_Y_OVERSHOOT, REVEAL_Y_REST, 1 - Math.pow(1 - ((t - 0.85) / 0.15), 2));
      materialsRef.current.forEach(m => m.opacity = Math.min(t / 0.85, 1));
      carRef.current.position.set(4, y, 2);
      if (revealProgress.current >= 1) revealDone.current = true;
      return;
    }

    topFactor.current = THREE.MathUtils.damp(topFactor.current, Math.max(0, 1 - scrollY / 150), 4, delta);
    smoothedProgress.current = THREE.MathUtils.damp(smoothedProgress.current, rawProgress, 2.5, delta);
    
    const targetX = THREE.MathUtils.lerp(4, -36, Math.pow(smoothedProgress.current, 3));
    carRef.current.position.set(targetX, REVEAL_Y_REST + (Math.sin(state.clock.getElapsedTime() * 1.5) * 0.08 * topFactor.current), 2);
    
    const targetRotY = (Math.PI / 5) + Math.PI + (Math.round(dragOffset.current / (Math.PI * 2)) * (Math.PI * 2)) + (0.18 * Math.pow(smoothedProgress.current, 3)) + (dragOffset.current * topFactor.current);
    carRef.current.rotation.y = THREE.MathUtils.damp(carRef.current.rotation.y, targetRotY, 5, delta);
  });

  return <primitive ref={carRef} object={scene} scale={BASE_SCALE} />;
}

export default function Background3DShell() {
  return (
    <div className="fixed inset-0 z-0 w-full h-full pointer-events-none">
      <Canvas camera={{ position: [0, 2, 8], fov: 45 }} gl={{ antialias: true, toneMappingExposure: 1.1 }}>
        <Environment preset="studio" />
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={0.9} />
        <ContactShadows position={[0, -1, 0]} opacity={0.32} blur={4.5} scale={20} />
        <React.Suspense fallback={null}><BmwModel /></React.Suspense>
      </Canvas>
    </div>
  );
}