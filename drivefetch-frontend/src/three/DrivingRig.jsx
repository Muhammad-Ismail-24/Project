import React, { useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF, OrbitControls } from '@react-three/drei';
import { useControls } from 'leva'; // LEVA (dev-only tuning) — removed at Step 14
import * as THREE from 'three';
import { progressRef } from './useScrollProgress';

// ─────────────────────────────────────────────────────────────────────────────
// THE DRIVING RIG (Blueprint §8.1–8.3)
//
// The car is a scroll-driven actor. Its transform is a PURE FUNCTION of
// progressRef.current, sampled from a CatmullRomCurve3 every frame in useFrame —
// no timer, no physics, no setState. Scrolling up reverses the drive perfectly
// by construction.
//
// Wheel motion (Option B, this asset's authored mechanism): the GLB has no
// separate per-wheel nodes — rims/tyres are single merged meshes — but it ships
// sharp rim meshes AND blurred rim meshes. We cross-fade sharp→blurred by
// |Δprogress|, so the wheels read as spinning while driving. Meshes are located
// once at load and stored in refs; the frame loop only reads refs + sets opacity
// (never traverses the graph).
// ─────────────────────────────────────────────────────────────────────────────

const MODEL_URL = '/bmwm5-optimized.glb';
const DRACO_PATH = '/draco/';
useGLTF.preload(MODEL_URL, DRACO_PATH);

const SCROLL_TAKEOVER = 0.02;

// Spline down the road centre: hero pose near camera → deep fog vanishing point.
// Gentle x/y variation gives the drive life while staying on the 16-wide road.
const CURVE = new THREE.CatmullRomCurve3(
  [
    new THREE.Vector3(0, 0, 4),
    new THREE.Vector3(0.6, 0.12, -25),
    new THREE.Vector3(-0.8, 0.2, -70),
    new THREE.Vector3(0.5, 0.1, -120),
    new THREE.Vector3(0, 0, -180),
  ],
  false,
  'catmullrom',
  0.5
);

// Camera settles to a stable down-the-road shot once the drive takes over, so
// the car recedes and vanishes into the fog (it is NOT chased).
const DRIVE_CAM_POS = new THREE.Vector3(2.5, 2.6, 9.5);
const DRIVE_CAM_LOOK = new THREE.Vector3(0, 0.6, -30);

// Node-name + material-name matchers. "trim" is excluded so carbon-trim body
// panels (…Trim…) are never mistaken for rims.
const RE_BLUR = /blur/i;
const RE_RIM = /(?:^|[^t])rim/i;
const RE_SKIP_PBR = /tyre|tire|glass|blur|(?:^|[^t])rim/i;

export default function DrivingRig() {
  const { scene } = useGLTF(MODEL_URL, DRACO_PATH);
  const carRef = useRef();
  const orbitRef = useRef();
  const blurMatsRef = useRef([]);
  const sharpMatsRef = useRef([]);
  const prevProgress = useRef(0);

  const tmpPoint = useMemo(() => new THREE.Vector3(), []);
  const tmpTangent = useMemo(() => new THREE.Vector3(), []);
  const tmpLook = useMemo(() => new THREE.Vector3(), []);

  // Dev-only tuning. Corrective rotation is exposed on all three axes (USD
  // exports can be multi-axis); seeds are guesses, dialed on a real screen.
  const { rotX, rotY, rotZ, posY, scale, speedFactor } = useControls('Car (dev)', {
    rotX: { value: -Math.PI / 2, min: -Math.PI, max: Math.PI, step: 0.01 },
    rotY: { value: Math.PI, min: -Math.PI, max: Math.PI, step: 0.01 },
    rotZ: { value: 0, min: -Math.PI, max: Math.PI, step: 0.01 },
    posY: { value: 0, min: -3, max: 3, step: 0.01 },
    scale: { value: 1.15, min: 0.2, max: 3, step: 0.01 },
    speedFactor: { value: 100, min: 0, max: 300, step: 1 },
  });

  // ONE-TIME traverse: PBR the body, collect + isolate rim materials.
  useLayoutEffect(() => {
    const blur = [];
    const sharp = [];
    scene.traverse((child) => {
      if (!child.isMesh || !child.material) return;
      child.castShadow = true;
      child.receiveShadow = true;
      const text = `${child.name} ${child.material.name || ''}`;

      if (RE_BLUR.test(text)) {
        child.material = child.material.clone();
        child.material.transparent = true;
        child.material.depthWrite = false;
        child.material.opacity = 0; // at rest: blurred rims hidden
        child.renderOrder = 2;
        blur.push(child.material);
      } else if (RE_RIM.test(text)) {
        child.material = child.material.clone();
        child.material.transparent = true;
        child.material.opacity = 1; // at rest: sharp rims visible
        sharp.push(child.material);
      } else if (!RE_SKIP_PBR.test(text)) {
        // Body panels → near-black metallic so the rims produce specular streaks.
        child.material.metalness = 0.9;
        child.material.roughness = 0.25;
        child.material.envMapIntensity = 1.1;
        child.material.needsUpdate = true;
      }
    });
    blurMatsRef.current = blur;
    sharpMatsRef.current = sharp;
  }, [scene]);

  useFrame((state, delta) => {
    if (!carRef.current) return;
    const p = THREE.MathUtils.clamp(progressRef.current, 0, 1);
    const orbitActive = p <= SCROLL_TAKEOVER;

    if (orbitRef.current) {
      orbitRef.current.enabled = orbitActive;
      if (!orbitActive) orbitRef.current.autoRotate = false;
    }

    // ── Car transform = pure function of progress (no timer / no state) ──
    if (orbitActive) {
      CURVE.getPointAt(0, tmpPoint);
      carRef.current.position.copy(tmpPoint);
      carRef.current.rotation.set(0, 0, 0); // nose points -Z via the inner corrective wrapper
    } else {
      CURVE.getPointAt(p, tmpPoint);
      CURVE.getTangentAt(p, tmpTangent);
      carRef.current.position.copy(tmpPoint);
      tmpLook.copy(tmpPoint).add(tmpTangent);
      carRef.current.lookAt(tmpLook); // aims local -Z (the corrected nose) down the tangent
    }

    // ── Wheel blur-swap: driven by Δprogress (refs only, no state) ──
    const dp = p - prevProgress.current;
    prevProgress.current = p;
    const blurAmt = Math.min(Math.abs(dp) * speedFactor, 1);
    const blurMats = blurMatsRef.current;
    const sharpMats = sharpMatsRef.current;
    for (let i = 0; i < blurMats.length; i++) blurMats[i].opacity = blurAmt;
    for (let i = 0; i < sharpMats.length; i++) sharpMats[i].opacity = 1 - blurAmt;

    // ── Camera: OrbitControls owns it at rest; on drive settle to a fixed
    //    down-the-road shot so the car recedes into the fog. ──
    if (!orbitActive) {
      const k = 1 - Math.pow(0.02, delta);
      state.camera.position.lerp(DRIVE_CAM_POS, k);
      state.camera.lookAt(DRIVE_CAM_LOOK);
    }
  });

  return (
    <>
      {/* Outer group: driven by the spline (position + lookAt). */}
      <group ref={carRef}>
        {/* Inner corrective wrapper: stands the USD-exported model upright and
            points its nose down wrapper-local -Z. Dialed via leva at Step 7. */}
        <group rotation={[rotX, rotY, rotZ]} position={[0, posY, 0]}>
          <primitive object={scene} scale={scale} />
        </group>
      </group>

      {/* Landing state (progress ≈ 0): free orbit, no pan/zoom, slow auto-rotate. */}
      <OrbitControls
        ref={orbitRef}
        enablePan={false}
        enableZoom={false}
        enableDamping
        dampingFactor={0.08}
        autoRotate
        autoRotateSpeed={0.5}
        target={[0, 0.6, 4]}
      />
    </>
  );
}
