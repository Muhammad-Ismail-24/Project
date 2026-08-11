import React, { useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF, Environment, Grid, MeshReflectorMaterial, OrbitControls, AdaptiveDpr } from '@react-three/drei';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';
import * as THREE from 'three';
import { progressRef } from '../three/useScrollProgress';

const MODEL_URL = '/bmwm5-optimized.glb';
const DRACO_PATH = '/draco/';

useGLTF.preload(MODEL_URL, DRACO_PATH);

// Hero 3/4 landing pose and the driving-away pose, tuned by eye against this
// GLB's forward axis (not a bare atan2 of the curve tangent — the model's
// own forward axis isn't world-aligned, so a small fixed sweep between two
// tuned angles reads truer than a raw tangent angle would).
const START_ANGLE = Math.PI / 5 + Math.PI;
const DRIVE_ANGLE = Math.PI + 0.12;
const SCROLL_TAKEOVER_EPSILON = 0.008;

// The invisible road the car drives down once scroll takes over. Starts at
// the landing-pose position so there is no pop when the takeover begins.
const ROAD_CURVE = new THREE.CatmullRomCurve3(
  [
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(-1.8, 0, -0.4),
    new THREE.Vector3(-4.5, 0, -1.0),
    new THREE.Vector3(-8, 0, -1.7),
    new THREE.Vector3(-11.5, 0, -2.2),
    new THREE.Vector3(-14.5, 0, -2.6),
  ],
  false,
  'catmullrom',
  0.4
);

const CHASE_OFFSET = new THREE.Vector3(3.2, 1.9, 4.6);

function CarModel({ orbitRef }) {
  const { scene } = useGLTF(MODEL_URL, DRACO_PATH);
  const carRef = useRef();
  const smoothedProgress = useRef(0);
  const tmpPoint = useMemo(() => new THREE.Vector3(), []);

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

  useFrame((state, delta) => {
    if (!carRef.current) return;

    smoothedProgress.current = THREE.MathUtils.damp(smoothedProgress.current, progressRef.current, 5, delta);
    const t = smoothedProgress.current;

    const orbitActive = t < SCROLL_TAKEOVER_EPSILON;
    if (orbitRef.current) {
      orbitRef.current.enabled = orbitActive;
      if (!orbitActive) orbitRef.current.autoRotate = false;
    }

    if (orbitActive) {
      carRef.current.position.set(0, 0, 0);
      carRef.current.rotation.y = START_ANGLE;
      return;
    }

    ROAD_CURVE.getPointAt(Math.min(t, 1), tmpPoint);
    carRef.current.position.copy(tmpPoint);
    carRef.current.rotation.y = THREE.MathUtils.lerp(START_ANGLE, DRIVE_ANGLE, Math.min(t * 3, 1));
  });

  return <primitive ref={carRef} object={scene} scale={1.15} rotation={[0, START_ANGLE, 0]} />;
}

// Subtle dolly/pan once the scroll takeover starts — OrbitControls owns the
// camera entirely during the landing state, so this only acts afterwards.
function CameraRig() {
  const smoothedProgress = useRef(0);
  const tmpCarPos = useMemo(() => new THREE.Vector3(), []);
  const tmpCamTarget = useMemo(() => new THREE.Vector3(), []);

  useFrame((state, delta) => {
    if (progressRef.current < SCROLL_TAKEOVER_EPSILON) return;

    smoothedProgress.current = THREE.MathUtils.damp(smoothedProgress.current, progressRef.current, 5, delta);
    const t = Math.min(smoothedProgress.current, 1);

    ROAD_CURVE.getPointAt(t, tmpCarPos);
    tmpCamTarget.copy(tmpCarPos).add(CHASE_OFFSET);

    state.camera.position.lerp(tmpCamTarget, 1 - Math.pow(0.001, delta));
    state.camera.lookAt(tmpCarPos.x, tmpCarPos.y + 0.4, tmpCarPos.z);
  });

  return null;
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
  const orbitRef = useRef();
  const reduceMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    []
  );

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

      <CarModel orbitRef={orbitRef} />
      <CameraRig />

      <OrbitControls
        ref={orbitRef}
        enablePan={false}
        enableZoom={false}
        enableDamping
        dampingFactor={0.08}
        autoRotate={!reduceMotion}
        autoRotateSpeed={0.5}
        target={[0, 0.4, 0]}
        onStart={() => {
          if (orbitRef.current) orbitRef.current.autoRotate = false;
        }}
      />

      <AdaptiveDpr pixelated />

      <EffectComposer multisampling={0}>
        <Bloom intensity={0.6} luminanceThreshold={0.7} mipmapBlur />
        <Vignette eskil={false} offset={0.15} darkness={0.6} />
      </EffectComposer>
    </>
  );
}
