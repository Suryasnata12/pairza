"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";

const RADIUS = 1.8;

function latLonToVector3(lat: number, lon: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  );
}

// Rough population-center approximations — this is an atmospheric backdrop,
// not a data visualization, so precision doesn't matter here.
const HOTSPOTS: [number, number][] = [
  [40.7, -74], [51.5, -0.1], [35.7, 139.7], [-33.9, 151.2], [1.35, 103.8],
  [19.4, -99.1], [-23.5, -46.6], [28.6, 77.2], [30.0, 31.2], [55.7, 37.6],
  [52.5, 13.4], [48.8, 2.3], [37.6, 126.9], [-1.3, 36.8], [13.7, 100.5],
  [39.9, 116.4], [-34.6, -58.4], [6.5, 3.4], [41.0, 28.9], [59.3, 18.1],
  [45.4, -75.7], [-37.8, 144.9], [25.2, 55.3], [14.6, 121.0], [23.1, 113.3],
];

function GlobeMesh() {
  const groupRef = useRef<THREE.Group>(null);
  const points = useMemo(() => HOTSPOTS.map(([lat, lon]) => latLonToVector3(lat, lon, RADIUS * 1.01)), []);

  const arcs = useMemo(() => {
    const pairs: [THREE.Vector3, THREE.Vector3][] = [];
    for (let i = 0; i < 7; i++) {
      const a = points[Math.floor(Math.random() * points.length)];
      const b = points[Math.floor(Math.random() * points.length)];
      if (a !== b) pairs.push([a, b]);
    }
    return pairs;
  }, [points]);

  useFrame((_, delta) => {
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.06;
  });

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[RADIUS, 48, 48]} />
        <meshBasicMaterial color="#14161f" wireframe transparent opacity={0.35} />
      </mesh>
      <mesh>
        <sphereGeometry args={[RADIUS * 0.985, 32, 32]} />
        <meshBasicMaterial color="#06070b" transparent opacity={0.9} />
      </mesh>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.018, 8, 8]} />
          <meshBasicMaterial color="#45e8c8" />
        </mesh>
      ))}
      {arcs.map(([a, b], i) => {
        const mid = a.clone().add(b).multiplyScalar(0.5).normalize().multiplyScalar(RADIUS * 1.35);
        const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        const pts = curve.getPoints(32);
        return <Line key={i} points={pts} color="#9b7bff" transparent opacity={0.45} lineWidth={1} />;
      })}
    </group>
  );
}

export function WorldGlobe({ className }: { className?: string }) {
  return (
    <div className={className} aria-hidden="true">
      <Canvas camera={{ position: [0, 0, 5], fov: 40 }} dpr={[1, 1.5]}>
        <ambientLight intensity={1} />
        <GlobeMesh />
      </Canvas>
    </div>
  );
}
