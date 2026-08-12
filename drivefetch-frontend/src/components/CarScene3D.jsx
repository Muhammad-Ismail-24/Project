import React from 'react';
import { AdaptiveDpr } from '@react-three/drei';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';
import Road from '../three/Road';
import LightRig from '../three/LightRig';
import DrivingRig from '../three/DrivingRig';

// Composition root (Blueprint §3): assembles the light rig, the road, and the
// scroll-driven car inside the persistent canvas, then the postprocessing pass.
export default function CarScene3D() {
  return (
    <>
      <LightRig />

      {/* Real road (Blueprint §7) — replaces the v1 helper grid. */}
      <Road mode="textured" />

      {/* Scroll-driven car + spline + orbit handoff (Blueprint §8). */}
      <DrivingRig />

      <AdaptiveDpr pixelated />

      {/* Postprocessing (§8.5): Bloom lifts only the rim highlights + road
          glow; Vignette darkens the corners for cinema framing. */}
      <EffectComposer multisampling={0}>
        <Bloom intensity={0.6} luminanceThreshold={0.7} mipmapBlur />
        <Vignette eskil={false} offset={0.15} darkness={0.6} />
      </EffectComposer>
    </>
  );
}
