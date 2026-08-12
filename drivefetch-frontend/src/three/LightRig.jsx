import React from 'react';
import { Environment } from '@react-three/drei';

// ─────────────────────────────────────────────────────────────────────────────
// THE LIGHT RIG (Blueprint §8.4) — cinematic pitch-black studio.
//
// Extracted from the scene so it is reusable and the composition root stays
// readable. The signature move: TWO rim lights from BEHIND carve the black car
// out of the dark. Renderer tone mapping (ACESFilmic, exposure 1.1, sRGB) and
// the transparent/near-black clear are set on the <Canvas> in Background3DShell.
// The car body PBR (metalness 0.9 / roughness 0.25) lives on the model in
// CarScene3D so rims produce sharp specular streaks.
// ─────────────────────────────────────────────────────────────────────────────
export default function LightRig() {
  return (
    <>
      {/* Low ambient fill so the front fascia isn't a pure void. */}
      <ambientLight intensity={0.15} />

      {/* Key rim — behind-left, cool white: carves the top edge out of the dark. */}
      <directionalLight position={[-6, 5, -4]} intensity={2.5} color="#cfe0ff" castShadow />

      {/* Secondary rim — behind-right, warmer. Two behind-rims = the black car pops. */}
      <directionalLight position={[6, 4, -3]} intensity={1.8} color="#fff0e0" />

      {/* Soft front fill. */}
      <directionalLight position={[0, 2, 6]} intensity={0.35} color="#e8e8f0" />

      {/* Faint accent under-glow low in front — brand kiss on the lower body. */}
      <pointLight position={[0, 0.3, 2.5]} intensity={0.8} color="#E5202E" distance={7} decay={2} />

      {/* Night HDRI at low intensity — seeds paint reflections without lifting
          the background (§8.4). Adds reflections only; if the preset asset fails
          to load, the rim lights still carry the scene. */}
      <Environment preset="night" environmentIntensity={0.4} />
    </>
  );
}
