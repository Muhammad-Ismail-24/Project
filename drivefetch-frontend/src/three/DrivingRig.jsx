import React, { useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { useControls } from 'leva'; // LEVA (dev-only tuning) — removed at Step 14
import * as THREE from 'three';
import { progressRef } from './useScrollProgress';

// ─────────────────────────────────────────────────────────────────────────────
// THE DRIVING RIG (Blueprint §8) — rebuilt per the static-camera spec.
//
// CAMERA: fixed in one place the whole journey (no spline on the camera). You
//   watch from a stable down-the-road viewpoint; only a tiny scroll-linked
//   vertical parallax drift, nothing more.
// SPLINE: governs ONLY the car. Start = hero park near camera, nose toward the
//   viewer; end = deep in the fog/clouds. Position + rotation are a PURE
//   FUNCTION of progressRef.current sampled every frame (no timer/physics/state)
//   → scroll-up reverses perfectly by construction.
// CLOUDS: layered procedural noise billboards (§ cloud-wall option A) the car
//   passes BEHIND and dissolves into — not just fog-shrink.
// WHEELS: sharp↔blurred cross-fade by |Δprogress|·speedFactor (kept).
// ─────────────────────────────────────────────────────────────────────────────

const MODEL_URL = '/bmwm5-optimized.glb';
const DRACO_PATH = '/draco/';
useGLTF.preload(MODEL_URL, DRACO_PATH);

// Car spline: hero park (z=+3, near camera) → deep behind the clouds (z=-200).
// Six control points for a smooth, lively-but-on-road path.
const CURVE = new THREE.CatmullRomCurve3(
  [
    new THREE.Vector3(0, 0, 3),
    new THREE.Vector3(0.4, 0.10, -30),
    new THREE.Vector3(-0.5, 0.15, -70),
    new THREE.Vector3(0.4, 0.10, -115),
    new THREE.Vector3(-0.2, 0.05, -160),
    new THREE.Vector3(0, 0, -200),
  ],
  false,
  'catmullrom',
  0.5
);
const SPLINE_LEN = CURVE.getLength();

// Static camera: a stable down-the-road shot. Never put on a curve.
const CAM_BASE = new THREE.Vector3(3, 2.4, 9.5);
const CAM_TARGET = new THREE.Vector3(0, 0.8, -50);

// Shared uv-passthrough vertex shader.
const VERT_UV = /* glsl */ `
  varying vec2 vUv;
  void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;

// Procedural cloud (fbm noise + radial edge fade so the quad edge is invisible).
const CLOUD_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform float uOpacity;
  uniform float uScale;
  uniform vec3  uColor;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
  float noise(vec2 p){
    vec2 i=floor(p), f=fract(p);
    float a=hash(i), b=hash(i+vec2(1.0,0.0)), c=hash(i+vec2(0.0,1.0)), d=hash(i+vec2(1.0,1.0));
    vec2 u=f*f*(3.0-2.0*f);
    return mix(mix(a,b,u.x),mix(c,d,u.x),u.y);
  }
  float fbm(vec2 p){ float v=0.0,a=0.5; for(int i=0;i<5;i++){ v+=a*noise(p); p*=2.02; a*=0.5; } return v; }
  void main(){
    vec2 uv = vUv * uScale;
    uv.x += uTime * 0.03;
    float n = fbm(uv + fbm(uv));
    vec2 c = vUv - 0.5;
    float edge = smoothstep(0.5, 0.12, length(c));   // fade toward the quad edges
    float alpha = smoothstep(0.32, 0.9, n) * edge * uOpacity;
    gl_FragColor = vec4(uColor, alpha);
  }
`;

// Deeper layers are wider / darker / thicker → a cloud bank the car sinks into.
const CLOUD_LAYERS = [
  { z: -120, w: 60, h: 30, color: [0.30, 0.31, 0.36], baseOp: 0.45, scale: 2.2 },
  { z: -145, w: 76, h: 38, color: [0.25, 0.26, 0.31], baseOp: 0.62, scale: 3.0 },
  { z: -170, w: 92, h: 46, color: [0.19, 0.20, 0.25], baseOp: 0.82, scale: 3.8 },
];

const RE_BLUR = /blur/i;
const RE_RIM = /(?:^|[^t])rim/i;
const RE_SKIP_PBR = /tyre|tire|glass|blur|(?:^|[^t])rim/i;

export default function DrivingRig() {
  const { scene } = useGLTF(MODEL_URL, DRACO_PATH);
  const carRef = useRef();
  const blurMatsRef = useRef([]);
  const sharpMatsRef = useRef([]);
  const prevProgress = useRef(0);
  const frameCount = useRef(0);

  const tmpPoint = useMemo(() => new THREE.Vector3(), []);
  const tmpCam = useMemo(() => new THREE.Vector3(), []);

  // Layered cloud materials built once; updated (uTime / uOpacity) each frame.
  const cloudLayers = useMemo(
    () =>
      CLOUD_LAYERS.map((cfg) => ({
        cfg,
        mat: new THREE.ShaderMaterial({
          vertexShader: VERT_UV,
          fragmentShader: CLOUD_FRAG,
          transparent: true,
          depthWrite: false,
          depthTest: true, // car is occluded only once it passes BEHIND the layer
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

  // Dev-only tuning. Corrective rotation on all three axes; seeds are guesses.
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

  useFrame((state, delta) => {
    if (!carRef.current) return;
    const p = THREE.MathUtils.clamp(progressRef.current, 0, 1);

    // ── Camera: STATIC base + tiny scroll parallax. No spline. ──
    tmpCam.copy(CAM_BASE);
    tmpCam.y += p * 0.5; // gentle vertical drift only
    state.camera.position.copy(tmpCam);
    state.camera.lookAt(CAM_TARGET);

    // ── Car transform = pure function of progress (no timer / no state) ──
    CURVE.getPointAt(p, tmpPoint);
    carRef.current.position.copy(tmpPoint);
    // Nose points TOWARD the camera (hero framing) throughout the recede.
    carRef.current.lookAt(state.camera.position);

    // ── Wheel blur-swap by Δprogress (refs only) ──
    const dp = p - prevProgress.current;
    prevProgress.current = p;
    const blurAmt = Math.min(Math.abs(dp) * speedFactor, 1);
    const blurMats = blurMatsRef.current;
    const sharpMats = sharpMatsRef.current;
    for (let i = 0; i < blurMats.length; i++) blurMats[i].opacity = blurAmt;
    for (let i = 0; i < sharpMats.length; i++) sharpMats[i].opacity = 1 - blurAmt;

    // ── Clouds: drift + thicken slightly with scroll ──
    for (let i = 0; i < cloudLayers.length; i++) {
      const u = cloudLayers[i].mat.uniforms;
      u.uTime.value += delta;
      u.uOpacity.value = cloudLayers[i].cfg.baseOp + p * 0.15;
    }

    // ── Smoothness instrumentation: [progress, dist-along-spline, car.pos] /5f ──
    if (import.meta.env.DEV) {
      frameCount.current += 1;
      if (frameCount.current % 5 === 0) {
        const q = carRef.current.position;
        // eslint-disable-next-line no-console
        console.log(
          `[DF drive] p=${p.toFixed(4)} dist=${(p * SPLINE_LEN).toFixed(2)} pos=(${q.x.toFixed(2)}, ${q.y.toFixed(2)}, ${q.z.toFixed(2)})`
        );
      }
    }
  });

  return (
    <>
      {/* Outer group: driven by the spline (position + lookAt-camera). */}
      <group ref={carRef}>
        {/* Inner corrective wrapper: stands the USD model upright, nose on -Z. */}
        <group rotation={[rotX, rotY, rotZ]} position={[0, posY, 0]}>
          <primitive object={scene} scale={scale} />
        </group>
      </group>

      {/* Volumetric cloud wall the car dissolves into (option A). */}
      {cloudLayers.map(({ cfg, mat }, i) => (
        <mesh key={i} position={[0, cfg.h * 0.32, cfg.z]} renderOrder={3}>
          <planeGeometry args={[cfg.w, cfg.h, 1, 1]} />
          <primitive object={mat} attach="material" />
        </mesh>
      ))}
    </>
  );
}
