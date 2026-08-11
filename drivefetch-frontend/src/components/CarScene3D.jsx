import React, { useLayoutEffect, useRef } from 'react';
import { useGLTF, Environment, Grid, MeshReflectorMaterial } from '@react-three/drei';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';

const MODEL_URL = '/bmwm5-optimized.glb';
const DRACO_PATH = '/draco/';

useGLTF.preload(MODEL_URL, DRACO_PATH);

export function CarModel(props) {
  const { scene } = useGLTF(MODEL_URL, DRACO_PATH);
  const carRef = useRef();

  useLayoutEffect(() => {
    scene.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
        if (child.material) {
          child.material.roughness = 0.25;
          child.material.metalness = 0.9;
          child.material.envMapIntensity = 1.1;
          child.material.needsUpdate = true;
        }
      }
    });
  }, [scene]);

  return <primitive ref={carRef} object={scene} scale={1.15} {...props} />;
}

function Floor() {
  return (
    <group position={[0, -0.01, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[60, 60]} />
        <MeshReflectorMaterial
          blur={[300, 80]}
          resolution={1024}
          mixBlur={1}
          mixStrength={35}
          roughness={1}
          depthScale={1.1}
          minDepthThreshold={0.85}
          color="#050506"
          metalness={0.6}
          mirror={0}
        />
      </mesh>
      <Grid
        position={[0, 0.001, 0]}
        args={[60, 60]}
        cellSize={0.6}
        cellThickness={0.5}
        cellColor="#2a2a33"
        sectionSize={3}
        sectionThickness={1}
        sectionColor="#E5202E"
        fadeDistance={26}
        fadeStrength={1.5}
        infiniteGrid
      />
    </group>
  );
}

export default function CarScene3D() {
  return (
    <>
      <ambientLight intensity={0.15} />

      {/* Key rim — behind-left, cool white: carves the top edge out of the dark */}
      <directionalLight position={[-6, 5, -4]} intensity={2.5} color="#cfe0ff" castShadow />

      {/* Secondary rim — behind-right, warmer */}
      <directionalLight position={[6, 4, -3]} intensity={1.8} color="#fff0e0" />

      {/* Soft front fill so the fascia isn't pure void */}
      <directionalLight position={[0, 2, 6]} intensity={0.35} color="#e8e8f0" />

      {/* Under-glow / floor bounce — brand red kiss on the lower body */}
      <pointLight position={[0, 0.3, 2.5]} intensity={0.8} color="#E5202E" distance={7} decay={2} />

      <Environment preset="warehouse" environmentIntensity={0.35} />

      <Floor />

      <CarModel position={[0, 0, 0]} rotation={[0, Math.PI * 0.82, 0]} />

      <EffectComposer multisampling={0}>
        <Bloom intensity={0.6} luminanceThreshold={0.7} mipmapBlur />
        <Vignette eskil={false} offset={0.15} darkness={0.6} />
      </EffectComposer>
    </>
  );
}
