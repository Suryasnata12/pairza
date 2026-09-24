"use client";

import { Component, type ReactNode } from "react";

/**
 * Second line of defense around <Canvas>, behind useWebGLSupported's feature check. That check
 * covers "WebGL isn't available at all"; this covers "WebGL claimed to be available but Three.js
 * still threw while actually using it" (a context lost mid-session, an unusual driver quirk,
 * etc.) — so a decorative background animation can never take the rest of the landing page down
 * with it, only itself.
 */
export class GlobeErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.warn("WorldGlobe failed to render; falling back to the static version.", error);
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
