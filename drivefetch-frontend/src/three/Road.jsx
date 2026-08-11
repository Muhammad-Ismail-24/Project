import React, { useLayoutEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useTexture } from '@react-three/drei';
import * as THREE from 'three';
import { progressRef } from './useScrollProgress';

// ─────────────────────────────────────────────────────────────────────────────
// THE ROAD (Blueprint §7) — a real road, not a helper grid.
//
// World layout: the road runs down world -Z toward the fog horizon. The car
// (Step 7 spline) drives forward into -Z and vanishes into the fog. Road and
// spline are co-oriented — that direction is decided here so Step 7 matches.
//
// Default mode is "textured" (the asphalt maps ship in public/textures/road).
// A genuine procedural ShaderMaterial base is provided behind mode="procedural"
// so the §7 prop-flag is real, not a stub. The streaming emissive lane markings
// and instanced edge reflectors are shared by both modes.
// ─────────────────────────────────────────────────────────────────────────────

const ROAD_LEN = 240;
const ROAD_WIDTH = 16;
const ROAD_CENTER_Z = -90; // spans z ∈ [+30 (near, behind hero car) .. -210 (deep fog)]
const NEAR_Z = ROAD_CENTER_Z + ROAD_LEN / 2; // +30
const FAR_Z = ROAD_CENTER_Z - ROAD_LEN / 2; //  -210
const TEX_BASE = '/textures/road/';

// ── Streaming lane markings ──────────────────────────────────────────────────
const LANE_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const LANE_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uProgress;
  uniform float uTime;
  uniform vec3  uDashColor;
  uniform vec3  uEdgeColor;
  void main() {
    vec2 uv = vUv;

    // uv.y runs into the distance. Subtracting a scroll-fed offset makes the
    // dashes rush toward the viewer -> conveys forward speed as you scroll.
    float stream = uProgress * 40.0 + uTime * 0.6;

    // Dashed centre line.
    float centerBand = smoothstep(0.011, 0.0, abs(uv.x - 0.5));
    float dash = step(0.5, fract(uv.y * 55.0 - stream));
    float center = centerBand * dash;

    // Solid glowing shoulder lines, subtly accent-tinted.
    float edgeL = smoothstep(0.013, 0.0, abs(uv.x - 0.045));
    float edgeR = smoothstep(0.013, 0.0, abs(uv.x - 0.955));
    float edge = max(edgeL, edgeR);

    vec3 col = uDashColor * center + uEdgeColor * edge;
    float alpha = max(center, edge);
    if (alpha < 0.02) discard;
    gl_FragColor = vec4(col, alpha);
  }
`;

function LaneMarkings() {
  const matRef = useRef();
  const uniforms = useMemo(
    () => ({
      uProgress: { value: 0 },
      uTime: { value: 0 },
      uDashColor: { value: new THREE.Color(1.7, 1.7, 1.5) }, // warm white, >1 so Bloom catches it
      uEdgeColor: { value: new THREE.Color(2.0, 0.35, 0.42) }, // accent-tinted, bloom
    }),
    []
  );

  useFrame((_, delta) => {
    if (!matRef.current) return;
    // Reads the scroll ref only — no React state (Core Performance Rule).
    matRef.current.uniforms.uProgress.value = progressRef.current;
    matRef.current.uniforms.uTime.value += delta;
  });

  return (
    <mesh position={[0, 0.02, ROAD_CENTER_Z]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[ROAD_WIDTH, ROAD_LEN, 1, 1]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={LANE_VERT}
        fragmentShader={LANE_FRAG}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}

// ── Instanced edge reflectors marching into the distance ─────────────────────
function EdgeReflectors({ count = 48 }) {
  const ref = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    if (!ref.current) return;
    const half = ROAD_WIDTH / 2 + 0.4;
    const perSide = count / 2;
    let i = 0;
    for (let s = 0; s < 2; s++) {
      const x = s === 0 ? -half : half;
      for (let k = 0; k < perSide; k++) {
        const z = THREE.MathUtils.lerp(NEAR_Z, FAR_Z, k / (perSide - 1));
        dummy.position.set(x, 0.15, z);
        dummy.updateMatrix();
        ref.current.setMatrixAt(i++, dummy.matrix);
      }
    }
    ref.current.instanceMatrix.needsUpdate = true;
  }, [count, dummy]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]} castShadow={false}>
      <boxGeometry args={[0.12, 0.3, 0.12]} />
      <meshStandardMaterial color="#1a0406" emissive="#E5202E" emissiveIntensity={2.2} toneMapped={false} />
    </instancedMesh>
  );
}

// ── Textured asphalt surface (default / shipping path) ───────────────────────
function RoadSurfaceTextured() {
  const { gl } = useThree();
  const [diffuse, normal, roughness] = useTexture([
    `${TEX_BASE}asphalt_diffuse.jpg`,
    `${TEX_BASE}asphalt_normal.jpg`,
    `${TEX_BASE}asphalt_roughness.jpg`,
  ]);

  useLayoutEffect(() => {
    const maxAniso = gl.capabilities.getMaxAnisotropy();
    [diffuse, normal, roughness].forEach((t) => {
      t.wrapS = THREE.RepeatWrapping;
      t.wrapT = THREE.RepeatWrapping;
      t.repeat.set(4, ROAD_LEN / 6);
      t.anisotropy = maxAniso;
      t.needsUpdate = true;
    });
    diffuse.colorSpace = THREE.SRGBColorSpace;
    normal.colorSpace = THREE.NoColorSpace;
    roughness.colorSpace = THREE.NoColorSpace;
  }, [diffuse, normal, roughness, gl]);

  return (
    <mesh position={[0, 0, ROAD_CENTER_Z]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[ROAD_WIDTH, ROAD_LEN, 1, 1]} />
      <meshStandardMaterial
        map={diffuse}
        normalMap={normal}
        roughnessMap={roughness}
        color="#33333a"
        roughness={1}
        metalness={0}
      />
    </mesh>
  );
}

// ── Procedural asphalt base (fallback behind mode="procedural") ──────────────
const PROC_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p){
    vec2 i = floor(p), f = fract(p);
    float a = hash(i), b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0)), d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }
  void main(){
    vec2 uv = vUv * vec2(8.0, 120.0);
    float g = noise(uv) * 0.6 + noise(uv * 3.0) * 0.4;
    vec3 base = vec3(0.078, 0.078, 0.094);   // ~#141418 dark asphalt
    base += (g - 0.5) * 0.03;                // subtle grain so it isn't a flat fill
    gl_FragColor = vec4(base, 1.0);
  }
`;

function RoadSurfaceProcedural() {
  const uniforms = useMemo(() => ({}), []);
  return (
    <mesh position={[0, 0, ROAD_CENTER_Z]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[ROAD_WIDTH, ROAD_LEN, 1, 1]} />
      <shaderMaterial vertexShader={LANE_VERT} fragmentShader={PROC_FRAG} uniforms={uniforms} />
    </mesh>
  );
}

export default function Road({ mode = 'textured' }) {
  return (
    <group>
      {mode === 'procedural' ? <RoadSurfaceProcedural /> : <RoadSurfaceTextured />}
      <LaneMarkings />
      <EdgeReflectors count={48} />
    </group>
  );
}
