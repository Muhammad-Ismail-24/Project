import React, { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { useControls } from 'leva'; // LEVA (dev-only tuning) — removed at Step 14
import * as THREE from 'three';
import { progressRef } from './useScrollProgress';

// ─────────────────────────────────────────────────────────────────────────────
// THE DRIVING RIG (Blueprint §8) — second rebuild, exact three-phase spec.
//
// Coordinate system (locked):
//   Road runs along Z; driving direction = -Z (into fog).
//   Parked  = (3, 0, 0), rotY = π/2 (side-profile hero).
//   Drive   = (0,0,0) → (0,0,-200).
// Camera is FIXED at [-2, 2.5, 8] looking toward [2, 0, -20] — never on a spline.
// Position + rotation are pure functions of progressRef.current across three
// phases (REST / PULLOUT / DRIVE) → scroll-up reverses perfectly.
// ─────────────────────────────────────────────────────────────────────────────

const MODEL_URL = '/bmwm5-optimized.glb';
const DRACO_PATH = '/draco/';
useGLTF.preload(MODEL_URL, DRACO_PATH);

const REST_END = 0.02;
const PULLOUT_END = 0.15;

const CAM_POS = new THREE.Vector3(-2, 2.5, 8);
const CAM_LOOK = new THREE.Vector3(2, 0, -20);

// Drive spline: road-centre, (0,0,0) → deep clouds (0,0,-200).
const CURVE = new THREE.CatmullRomCurve3(
  [
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(0.35, 0.08, -35),
    new THREE.Vector3(-0.4, 0.12, -80),
    new THREE.Vector3(0.3, 0.08, -130),
    new THREE.Vector3(-0.15, 0.04, -170),
    new THREE.Vector3(0, 0, -200),
  ],
  false,
  'catmullrom',
  0.5
);
const SPLINE_LEN = CURVE.getLength();

// Parked pose and drive-start pose as quaternions (Phase 2 slerps between them).
const PARKED_QUAT = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, Math.PI / 2, 0));
const DRIVE_START_QUAT = (() => {
  const o = new THREE.Object3D();
  const t0 = CURVE.getTangentAt(0);
  o.position.set(0, 0, 0);
  o.lookAt(t0.x, t0.y, t0.z);
  return o.quaternion.clone();
})();

const smoothstep = (t) => {
  const x = Math.min(Math.max(t, 0), 1);
  return x * x * (3 - 2 * x);
};

// Shared uv-passthrough vertex shader + procedural cloud fragment (fbm noise).
const VERT_UV = /* glsl */ `
  varying vec2 vUv;
  void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;
const CLOUD_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime; uniform float uOpacity; uniform float uScale; uniform vec3 uColor;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
  float noise(vec2 p){
    vec2 i=floor(p), f=fract(p);
    float a=hash(i), b=hash(i+vec2(1.0,0.0)), c=hash(i+vec2(0.0,1.0)), d=hash(i+vec2(1.0,1.0));
    vec2 u=f*f*(3.0-2.0*f);
    return mix(mix(a,b,u.x),mix(c,d,u.x),u.y);
  }
  float fbm(vec2 p){ float v=0.0,a=0.5; for(int i=0;i<5;i++){ v+=a*noise(p); p*=2.02; a*=0.5; } return v; }
  void main(){
    vec2 uv = vUv * uScale; uv.x += uTime * 0.03;
    float n = fbm(uv + fbm(uv));
    vec2 c = vUv - 0.5;
    float edge = smoothstep(0.5, 0.12, length(c));
    float alpha = smoothstep(0.32, 0.9, n) * edge * uOpacity;
    gl_FragColor = vec4(uColor, alpha);
  }
`;
// Cloud wall around z ≈ -160 so the car (→ -200) drives into it and dissolves.
const CLOUD_LAYERS = [
  { z: -150, w: 64, h: 32, color: [0.30, 0.31, 0.36], baseOp: 0.45, scale: 2.4 },
  { z: -162, w: 80, h: 40, color: [0.25, 0.26, 0.31], baseOp: 0.62, scale: 3.1 },
  { z: -174, w: 96, h: 48, color: [0.19, 0.20, 0.25], baseOp: 0.82, scale: 3.9 },
];

const RE_BLUR = /blur/i;
const RE_RIM = /(?:^|[^t])rim/i;
const RE_SKIP_PBR = /tyre|tire|glass|blur|(?:^|[^t])rim/i;

export default function DrivingRig() {
  const { scene } = useGLTF(MODEL_URL, DRACO_PATH);
  const { camera } = useThree();
  const carRef = useRef();
  const blurMatsRef = useRef([]);
  const sharpMatsRef = useRef([]);
  const prevProgress = useRef(0);
  const frameCount = useRef(0);

  // Interactive rest-state rotation (refs, never state).
  const isDragging = useRef(false);
  const dragOffset = useRef(0);
  const autoRotate = useRef(0);
  const lastX = useRef(0);
  const leftRest = useRef(false);
  const dragSpeedRef = useRef(0.005);

  const tmpPoint = useMemo(() => new THREE.Vector3(), []);
  const tmpTangent = useMemo(() => new THREE.Vector3(), []);
  const tmpLook = useMemo(() => new THREE.Vector3(), []);
  const tmpEuler = useMemo(() => new THREE.Euler(), []);

  const cloudLayers = useMemo(
    () =>
      CLOUD_LAYERS.map((cfg) => ({
        cfg,
        mat: new THREE.ShaderMaterial({
          vertexShader: VERT_UV,
          fragmentShader: CLOUD_FRAG,
          transparent: true,
          depthWrite: false,
          depthTest: true,
          uniforms: {
            uTime: { value: Math.random() * 10 },
            uOpacity: { value: cfg.baseOp },
            uScale: { value: cfg.scale },
            uColor: { value: new THREE.Color(cfg.color[0], cfg.color[1], cfg.color[2]) },
          },
        }),
      })),
    []
  );

  const { rotX, rotY, rotZ, posY, scale, dragSpeed, speedFactor } = useControls('Car (dev)', {
    rotX: { value: 0, min: -Math.PI, max: Math.PI, step: 0.01 },
    rotY: { value: 0, min: -Math.PI, max: Math.PI, step: 0.01 },
    rotZ: { value: 0, min: -Math.PI, max: Math.PI, step: 0.01 },
    posY: { value: 0, min: -3, max: 3, step: 0.01 },
    scale: { value: 1.0, min: 0.2, max: 3, step: 0.01 },
    dragSpeed: { value: 0.005, min: 0, max: 0.03, step: 0.001 },
    speedFactor: { value: 100, min: 0, max: 300, step: 1 },
  });
  dragSpeedRef.current = dragSpeed;

  // Fixed camera — set once, never animated.
  useLayoutEffect(() => {
    camera.position.copy(CAM_POS);
    camera.lookAt(CAM_LOOK);
  }, [camera]);

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
        child.material.opacity = 0;
        child.renderOrder = 2;
        blur.push(child.material);
      } else if (RE_RIM.test(text)) {
        child.material = child.material.clone();
        child.material.transparent = true;
        child.material.opacity = 1;
        sharp.push(child.material);
      } else if (!RE_SKIP_PBR.test(text)) {
        child.material.metalness = 0.9;
        child.material.roughness = 0.25;
        child.material.envMapIntensity = 1.1;
        child.material.needsUpdate = true;
      }
    });
    blurMatsRef.current = blur;
    sharpMatsRef.current = sharp;
  }, [scene]);

  // ── Y-axis drag on the car group. Move/up on window for the drag's duration. ──
  const onMove = useMemo(
    () => (e) => {
      if (!isDragging.current) return;
      const x = e.clientX;
      dragOffset.current += (x - lastX.current) * dragSpeedRef.current;
      lastX.current = x;
    },
    []
  );
  const onUp = useMemo(
    () => () => {
      isDragging.current = false;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    },
    [onMove]
  );
  const onPointerDownCar = (e) => {
    if (progressRef.current > REST_END) return; // drag only during REST
    e.stopPropagation();
    isDragging.current = true;
    lastX.current = e.clientX;
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };
  useEffect(
    () => () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    },
    [onMove, onUp]
  );

  useFrame((state, delta) => {
    if (!carRef.current) return;
    const p = THREE.MathUtils.clamp(progressRef.current, 0, 1);

    // Reset interactive offsets once when leaving REST (Phase 2 takes control).
    if (p > REST_END) {
      if (!leftRest.current) {
        dragOffset.current = 0;
        autoRotate.current = 0;
        isDragging.current = false;
        leftRest.current = true;
      }
    } else {
      leftRest.current = false;
    }

    let phase;
    if (p <= REST_END) {
      // ── Phase 1: REST — parked side-profile, drag + auto-rotate. ──
      phase = 1;
      if (!isDragging.current) autoRotate.current += 0.003;
      const yaw = Math.PI / 2 + dragOffset.current + autoRotate.current;
      carRef.current.position.set(3, 0, 0);
      carRef.current.quaternion.setFromEuler(tmpEuler.set(0, yaw, 0));
    } else if (p <= PULLOUT_END) {
      // ── Phase 2: PULLOUT — smoothstep position, quaternion slerp rotation. ──
      phase = 2;
      const sub = smoothstep((p - REST_END) / (PULLOUT_END - REST_END));
      carRef.current.position.set(THREE.MathUtils.lerp(3, 0, sub), 0, 0);
      carRef.current.quaternion.slerpQuaternions(PARKED_QUAT, DRIVE_START_QUAT, sub);
    } else {
      // ── Phase 3: DRIVE — pure spline follow, tangent lookAt into -Z. ──
      phase = 3;
      const dp = (p - PULLOUT_END) / (1 - PULLOUT_END);
      CURVE.getPointAt(dp, tmpPoint);
      CURVE.getTangentAt(dp, tmpTangent);
      carRef.current.position.copy(tmpPoint);
      tmpLook.copy(tmpPoint).add(tmpTangent);
      carRef.current.lookAt(tmpLook);
    }

    // ── Wheel blur-swap by Δprogress (refs only). ──
    const dprog = p - prevProgress.current;
    prevProgress.current = p;
    const blurAmt = Math.min(Math.abs(dprog) * speedFactor, 1);
    const blurMats = blurMatsRef.current;
    const sharpMats = sharpMatsRef.current;
    for (let i = 0; i < blurMats.length; i++) blurMats[i].opacity = blurAmt;
    for (let i = 0; i < sharpMats.length; i++) sharpMats[i].opacity = 1 - blurAmt;

    // ── Clouds: drift + thicken slightly with scroll. ──
    for (let i = 0; i < cloudLayers.length; i++) {
      const u = cloudLayers[i].mat.uniforms;
      u.uTime.value += delta;
      u.uOpacity.value = cloudLayers[i].cfg.baseOp + p * 0.15;
    }

    // ── Smoothness log (DEV) — read on a real screen; rAF is paused when hidden. ──
    if (import.meta.env.DEV) {
      frameCount.current += 1;
      if (frameCount.current % 5 === 0) {
        // eslint-disable-next-line no-console
        console.log(`[DF drive] p=${p.toFixed(4)} phase=${phase} z=${carRef.current.position.z.toFixed(2)} dist=${(p * SPLINE_LEN).toFixed(1)}`);
      }
    }
  });

  return (
    <>
      {/* Outer group: driven by the three phases. Drag starts on the car. */}
      <group ref={carRef} onPointerDown={onPointerDownCar}>
        {/* Inner corrective wrapper (leva) + wheel-height posY. */}
        <group rotation={[rotX, rotY, rotZ]} position={[0, posY, 0]}>
          <primitive object={scene} scale={scale} />
        </group>
      </group>

      {/* Volumetric cloud wall the car dissolves into. */}
      {cloudLayers.map(({ cfg, mat }, i) => (
        <mesh key={i} position={[0, cfg.h * 0.28, cfg.z]} renderOrder={3}>
          <planeGeometry args={[cfg.w, cfg.h, 1, 1]} />
          <primitive object={mat} attach="material" />
        </mesh>
      ))}
    </>
  );
}
