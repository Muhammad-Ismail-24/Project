import React, { useRef, useLayoutEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Environment, ContactShadows, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

function BmwModel() {
  const { scene } = useGLTF('/bmwm5.glb');
  const carRef = useRef();
  
  // Track smoothed progress natively (NO React State)
  const smoothedProgress = useRef(0);

  useLayoutEffect(() => {
    scene.traverse((child) => {
      if (child.isMesh) {
        child.material = new THREE.MeshStandardMaterial({
          color: '#050505',
          roughness: 0.15,
          metalness: 0.8,
          envMapIntensity: 2.5, 
        });
      }
    });
  }, [scene]);

  useFrame((state, delta) => {
    if (!carRef.current) return;

    // 1. READ RAW SCROLL DIRECTLY FROM DOM
    // This bypasses React's asynchronous state delays entirely
    const scrollY = window.scrollY;
    const maxScroll = document.body.scrollHeight - window.innerHeight;
    const rawProgress = maxScroll > 0 ? (scrollY / maxScroll) : 0;

    // 2. DAMP THE PROGRESS
    smoothedProgress.current = THREE.MathUtils.damp(
      smoothedProgress.current, 
      rawProgress, 
      2.5, // Damping weight
      delta
    );

    // 3. RIGID LERP MATH
    const currentX = THREE.MathUtils.lerp(4, -15, smoothedProgress.current);
    const currentZ = THREE.MathUtils.lerp(2, -2, smoothedProgress.current);
    
    const startAngle = (Math.PI / 5) + Math.PI; 
    const endAngle = (Math.PI / 1.5) + Math.PI;
    const currentRotationY = THREE.MathUtils.lerp(startAngle, endAngle, smoothedProgress.current);

    // 4. DIRECT ASSIGNMENT (Zero drift)
    carRef.current.position.set(currentX, -1, currentZ);
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
    <div id="canvas-container" className="fixed inset-0 z-0 w-full h-full pointer-events-none">
      <Canvas 
        camera={{ position: [0, 2, 8], fov: 45 }} 
        gl={{ antialias: true, toneMappingExposure: 1.2 }}
      >
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