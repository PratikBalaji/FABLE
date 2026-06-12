"use client";
import React, { useRef, useMemo, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Stars, Text, Billboard, Line } from "@react-three/drei";
import * as THREE from "three";
import type { GraphNode, GraphEdge, GraphState } from "@/lib/api";

// ---------------------------------------------------------------------------
// P5a perf fixes (vs original):
//   1. Geometries hoisted to module scope — single GPU upload instead of one per
//      node per mount.
//   2. Position arrays memoized on primitive coords (was new array each render).
//   3. Single `useFrame` in Scene root drives all per-node animation via refs
//      (was N closures per scene = N×60fps work).
//   4. Canvas dpr clamped to [1, 2] (was uncapped → 4-9× pixel cost on retina).
//   5. Starfield count 500 / 300 (was 3000 / 2000).
//   6. Orbital particles 12 max per cluster, top-5 clusters max (was 50 each, all).
//   7. Top-K node cap (default 30) keeps the scene bounded as the graph grows.
//   8. Module-level dispose hook cleans shared geometries on app unmount.
//   9. `EdgeBeam.points` memoized on primitive numeric coords (was object refs →
//      stale on parent rerender).
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<string, string> = {
  cluster: "#cba6f7",
  concept: "#89b4fa",
  model:   "#a6e3a1",
  domain:  "#f9e2af",
};

const EDGE_COLORS: Record<string, string> = {
  related:          "#585b70",
  co_occurs:        "#45475a",
  model_excels_at:  "#a6e3a1",
  derived_from:     "#89b4fa",
};

// Tunables
const TOP_K_NODES = 30;
const MAX_PARTICLE_CLUSTERS = 5;
const MAX_PARTICLES_PER_CLUSTER = 12;

// Module-scope geometries — uploaded to the GPU exactly once.
const GEOM_SPHERE_MAIN = new THREE.SphereGeometry(1, 16, 16);   // was 32×32 per node
const GEOM_SPHERE_GLOW = new THREE.SphereGeometry(1, 12, 12);
const GEOM_RING        = new THREE.TorusGeometry(1, 0.015, 6, 32);

// ---------------------------------------------------------------------------
// PlanetNode — no per-node useFrame; animation driven by Scene.
// ---------------------------------------------------------------------------
const RING_ROTATION: [number, number, number] = [Math.PI / 2, 0, 0];

interface PlanetNodeProps {
  node: GraphNode;
  registerRef: (id: string, mesh: THREE.Mesh | null, glow: THREE.Mesh | null, weight: number) => void;
}

function PlanetNode({ node, registerRef }: PlanetNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const color = TYPE_COLORS[node.type] || "#cdd6f4";

  const baseSize = useMemo(() => (
    node.type === "cluster"
      ? 0.4 + Math.min(node.weight, 10) * 0.08
      : 0.12 + Math.min(node.weight, 10) * 0.03
  ), [node.type, node.weight]);

  // Memoize on primitive coords so referential equality holds across renders.
  const position = useMemo<[number, number, number]>(
    () => [node.position.x, node.position.y, node.position.z],
    [node.position.x, node.position.y, node.position.z],
  );

  const labelOffset = useMemo<[number, number, number]>(
    () => [0, baseSize + 0.2, 0],
    [baseSize],
  );

  const runCountOffset = useMemo<[number, number, number]>(
    () => [0, baseSize + 0.08, 0],
    [baseSize],
  );

  // Register refs with parent so a single useFrame can animate everything.
  useEffect(() => {
    registerRef(node.id, meshRef.current, glowRef.current, node.weight);
    return () => registerRef(node.id, null, null, node.weight);
  }, [node.id, node.weight, registerRef]);

  return (
    <group position={position}>
      <mesh ref={glowRef} geometry={GEOM_SPHERE_GLOW} scale={baseSize * 1.5}>
        <meshBasicMaterial color={color} transparent opacity={0.15} />
      </mesh>
      <mesh ref={meshRef} geometry={GEOM_SPHERE_MAIN} scale={baseSize}>
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={1.2}
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>
      {node.type === "cluster" && (
        <mesh geometry={GEOM_RING} rotation={RING_ROTATION} scale={baseSize * 1.8}>
          <meshBasicMaterial color={color} transparent opacity={0.4} />
        </mesh>
      )}
      <Billboard>
        <Text
          position={labelOffset}
          fontSize={0.12}
          color="#cdd6f4"
          anchorX="center"
          anchorY="bottom"
          outlineColor="#000000"
          outlineWidth={0.01}
        >
          {node.label.length > 18 ? node.label.slice(0, 18) + "..." : node.label}
        </Text>
        {node.runCount > 0 && (
          <Text
            position={runCountOffset}
            fontSize={0.07}
            color="#6c7086"
            anchorX="center"
          >
            {`${node.runCount} runs`}
          </Text>
        )}
      </Billboard>
    </group>
  );
}

// ---------------------------------------------------------------------------
// EdgeBeam — memoized on primitive coords (not object refs).
// ---------------------------------------------------------------------------
function EdgeBeam({ edge, nodes }: { edge: GraphEdge; nodes: Map<string, GraphNode> }) {
  const source = nodes.get(edge.source);
  const target = nodes.get(edge.target);

  const points = useMemo(() => {
    if (!source || !target) return null;
    return [
      new THREE.Vector3(source.position.x, source.position.y, source.position.z),
      new THREE.Vector3(target.position.x, target.position.y, target.position.z),
    ];
  }, [
    source?.position.x, source?.position.y, source?.position.z,
    target?.position.x, target?.position.y, target?.position.z,
  ]);

  if (!points) return null;

  const color = EDGE_COLORS[edge.type] || "#45475a";
  const opacity = Math.min(0.3 + edge.weight * 0.1, 0.9);

  return (
    <Line
      points={points}
      color={color}
      lineWidth={Math.min(0.5 + edge.weight * 0.3, 3)}
      transparent
      opacity={opacity}
    />
  );
}

// ---------------------------------------------------------------------------
// OrbitalParticles — cap per cluster + limit total active clusters in caller.
// ---------------------------------------------------------------------------
function OrbitalParticles({ node }: { node: GraphNode }) {
  const ref = useRef<THREE.Points>(null);
  const count = Math.min(node.runCount * 2, MAX_PARTICLES_PER_CLUSTER);

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const radius = 0.4 + (i % 7) / 30;
      arr[i * 3]     = Math.cos(angle) * radius;
      arr[i * 3 + 1] = (((i * 37) % 100) / 100 - 0.5) * 0.2;
      arr[i * 3 + 2] = Math.sin(angle) * radius;
    }
    return arr;
  }, [count]);

  const position = useMemo<[number, number, number]>(
    () => [node.position.x, node.position.y, node.position.z],
    [node.position.x, node.position.y, node.position.z],
  );

  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y = state.clock.elapsedTime * 0.5;
    }
  });

  if (count === 0) return null;

  return (
    <points ref={ref} position={position}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.02}
        color={TYPE_COLORS[node.type] || "#cdd6f4"}
        transparent
        opacity={0.6}
        sizeAttenuation
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// Scene — single useFrame for ALL node animation.
// ---------------------------------------------------------------------------
interface NodeAnim {
  mesh: THREE.Mesh | null;
  glow: THREE.Mesh | null;
  weight: number;
}

function Scene({ graphState }: { graphState: GraphState }) {
  // Top-K filter so the scene stays bounded.
  const topNodes = useMemo(() => {
    const sorted = [...graphState.nodes].sort((a, b) => b.weight - a.weight);
    return sorted.slice(0, TOP_K_NODES);
  }, [graphState.nodes]);

  const nodeMap = useMemo(
    () => new Map(topNodes.map((n) => [n.id, n])),
    [topNodes],
  );

  // Edges are kept only when both ends are visible (post top-K filter).
  const visibleEdges = useMemo(
    () => graphState.edges.filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target)),
    [graphState.edges, nodeMap],
  );

  // Active clusters for orbital particles — capped.
  const activeClusters = useMemo(
    () =>
      topNodes
        .filter((n) => n.type === "cluster" && n.runCount > 0)
        .slice(0, MAX_PARTICLE_CLUSTERS),
    [topNodes],
  );

  // Animation registry — populated by PlanetNode children via callback.
  const animRefs = useRef<Map<string, NodeAnim>>(new Map());
  const registerRef = useMemo(() => (
    (id: string, mesh: THREE.Mesh | null, glow: THREE.Mesh | null, weight: number) => {
      if (!mesh && !glow) {
        animRefs.current.delete(id);
      } else {
        animRefs.current.set(id, { mesh, glow, weight });
      }
    }
  ), []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const glowScale = 1.4 + Math.sin(t * 1.5) * 0.2;
    animRefs.current.forEach((rec) => {
      if (rec.mesh) {
        rec.mesh.rotation.y = t * 0.3;
        const pulse = 1 + Math.sin(t * 2 + rec.weight) * 0.05;
        rec.mesh.scale.setScalar(pulse * (rec.mesh.userData.baseScale ?? 1));
      }
      if (rec.glow) {
        rec.glow.scale.setScalar(glowScale * (rec.glow.userData.baseScale ?? 1));
      }
    });
  });

  const hiddenCount = graphState.nodes.length - topNodes.length;

  return (
    <>
      <ambientLight intensity={0.15} />
      <pointLight position={[0, 5, 0]} intensity={3} color="#cba6f7" />
      <pointLight position={[5, -3, 5]} intensity={2} color="#89b4fa" />
      <pointLight position={[-5, 2, -5]} intensity={1.5} color="#f38ba8" />

      <Stars radius={50} depth={80} count={500} factor={3} saturation={0.2} fade speed={0.5} />

      {visibleEdges.map((edge, i) => (
        <EdgeBeam key={`${edge.source}-${edge.target}-${i}`} edge={edge} nodes={nodeMap} />
      ))}

      {topNodes.map((node) => (
        <PlanetNode key={node.id} node={node} registerRef={registerRef} />
      ))}

      {activeClusters.map((node) => (
        <OrbitalParticles key={`particles-${node.id}`} node={node} />
      ))}

      {/* Central star — uses shared geometry */}
      <mesh position={[0, 0, 0]} geometry={GEOM_SPHERE_MAIN} scale={0.2}>
        <meshBasicMaterial color="#cba6f7" />
      </mesh>
      <mesh position={[0, 0, 0]} geometry={GEOM_SPHERE_GLOW} scale={0.5}>
        <meshBasicMaterial color="#cba6f7" transparent opacity={0.15} />
      </mesh>
      <pointLight position={[0, 0, 0]} intensity={5} color="#cba6f7" distance={20} />

      {hiddenCount > 0 && (
        <Billboard position={[0, -2.5, 0]}>
          <Text fontSize={0.1} color="#6c7086" anchorX="center">
            {`+${hiddenCount} more nodes hidden (top ${TOP_K_NODES} shown)`}
          </Text>
        </Billboard>
      )}

      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
        minDistance={2}
        maxDistance={30}
        autoRotate
        autoRotateSpeed={0.3}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Empty state — slimmer starfield.
// ---------------------------------------------------------------------------
function EmptyState() {
  return (
    <>
      <ambientLight intensity={0.1} />
      <Stars radius={50} depth={80} count={300} factor={3} saturation={0.1} fade speed={0.3} />
      <mesh position={[0, 0, 0]} geometry={GEOM_SPHERE_MAIN} scale={0.15}>
        <meshStandardMaterial color="#cba6f7" emissive="#cba6f7" emissiveIntensity={0.5} />
      </mesh>
      <Billboard position={[0, 0.5, 0]}>
        <Text fontSize={0.15} color="#6c7086" anchorX="center">
          Run a task to grow the knowledge universe...
        </Text>
      </Billboard>
      <OrbitControls autoRotate autoRotateSpeed={0.5} enableDamping dampingFactor={0.08} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Main export.
// ---------------------------------------------------------------------------
interface Props {
  graphState: GraphState | null;
}

export default function PlanetaryGraph({ graphState }: Props) {
  const hasData = graphState && graphState.nodes.length > 0;

  // Dispose shared geometries when the page unmounts (HMR + route changes).
  useEffect(() => {
    return () => {
      GEOM_SPHERE_MAIN.dispose();
      GEOM_SPHERE_GLOW.dispose();
      GEOM_RING.dispose();
    };
  }, []);

  return (
    <div className="w-full h-full bg-crust rounded-lg overflow-hidden border border-surface0">
      <Canvas
        camera={{ position: [3, 2, 3], fov: 65, near: 0.1, far: 100 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
        style={{ background: "#11111b" }}
      >
        {hasData ? <Scene graphState={graphState} /> : <EmptyState />}
      </Canvas>

      {graphState?.stats && (
        <div className="absolute bottom-3 left-3 bg-crust/80 backdrop-blur border border-surface0 rounded px-3 py-2 text-xs font-mono space-y-0.5">
          <div className="text-accent font-bold">KNOWLEDGE ENGINE</div>
          <div className="text-subtext">{graphState.stats.totalRuns} runs processed</div>
          <div className="text-subtext">{graphState.stats.clusters} planets &middot; {graphState.stats.concepts} concepts</div>
          <div className="text-subtext">{graphState.stats.totalEdges} connections</div>
        </div>
      )}
    </div>
  );
}
