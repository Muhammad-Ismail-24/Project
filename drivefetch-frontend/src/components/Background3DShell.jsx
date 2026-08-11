import React, { Suspense, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei';
import * as THREE from 'three';
import CarScene3D from './CarScene3D';

// Mounted exactly once, by MainLayout, fixed behind all routes. Route
// changes swap the DOM overlay only — this Canvas and its WebGL context
// persist across navigation.
export default function Background3DShell() {
  const [dpr, setDpr] = useState(1.5);

  return (
    <div className="fixed inset-0 z-0 w-full h-full bg-void">
      <Canvas
        dpr={dpr}
        shadows
        camera={{ position: [4.5, 2.2, 7], fov: 40 }}
        gl={{
          antialias: true,
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.1,
          outputColorSpace: THREE.SRGBColorSpace,
        }}
      >
        <color attach="background" args={['#050506']} />
        {/* Fog in --df-void so the road fades into darkness at the horizon and
            the far mesh edge is never visible (Blueprint §7.5). Tuned to the
            240-unit road: near road clear, distance swallowed by ~z -140. */}
        <fog attach="fog" args={['#050506', 25, 150]} />
        <PerformanceMonitor onIncline={() => setDpr(2)} onDecline={() => setDpr(1)} />
        <Suspense fallback={null}>
          <CarScene3D />
        </Suspense>
      </Canvas>
    </div>
  );
}
