"use client";

import { useEffect, useState } from "react";

/**
 * True/false once checked, null while still checking (always null during server render, so the
 * first client render matches — the 3D globe simply doesn't exist in the DOM until this settles,
 * rather than flashing and then disappearing).
 *
 * Some browser configurations report a WebGL context as available but then fail to actually
 * create one when a real @react-three/fiber <Canvas> tries — Chrome with hardware acceleration
 * fully disabled (GPU process unavailable, not just a slow one) is a real case of this, not a
 * hypothetical. That failure was previously happening repeatedly inside <Canvas> itself with no
 * feature check up front, which could crash the tab's renderer process outright (seen as
 * Chrome's own "This page couldn't load" screen, not a React error) rather than failing gracefully.
 * A single throwaway canvas here decides WebGL support before the real one is ever created, so a
 * browser that can't do WebGL simply gets the CSS fallback and the real Canvas is never mounted.
 */
export function useWebGLSupported(): boolean | null {
  const [supported, setSupported] = useState<boolean | null>(null);

  useEffect(() => {
    try {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      setSupported(gl !== null);
    } catch {
      setSupported(false);
    }
  }, []);

  return supported;
}
