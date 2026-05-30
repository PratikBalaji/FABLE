"use client";
import React, { useRef, useMemo, useEffect } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Stars, Text, Billboard, Line } from "@react-three/drei";
// import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import type { GraphNode, GraphEdge, GraphState } from "@/lib/api";

// -- Color palette --
const TYPE_COLORS: Record<string, string> = {
  cluster: "#cba6f7",   // mauve / purple
  concept: "#89b4fa",   // blue
  model:   "#a6e3a1",   // green
  domain:  "#f9e2af",   // yellow
};

const EDGE_COLORS: Record<string, string> = {
  related:          "#585b70",
  co_occurs:        "#45475a",
  model_excels_at:  "#a6e3a1",
  derived_from:     "#89b4fa",
};

// -- Planet node --
function PlanetNode({ node }: { node: GraphNode }) {
  const meshRef = useRef<THREE.Mesh>(null!);
  const glowRef = useRef<THREE.Mesh>(null!);
  const color = TYPE_COLORS[node.type] || "#cdd6f4";
  const baseSize = node.type === "cluster"
    ? 0.4 + Math.min(node.weight, 10) * 0.08
    : 0.12 + Math.min(node.weight, 10) * 0.03;

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (meshRef.current) {
      // Gentle rotation
      meshRef.current.rotation.y = t * 0.3;
      // Subtle pulse based on weight
      const pulse = 1 + Math.sin(t * 2 + node.weight) * 0.05;
      meshRef.current.scale.setScalar(pulse);
    }
    if (glowRef.current) {
      // Glow breathes
      const glow = 1.4 + Math.sin(t * 1.5) * 0.2;
      glowRef.current.scale.setScalar(glow);
    }
  });

  return (
    <group position={[node.position.x, node.position.y, node.position.z]}>
      {/* Glow sphere */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[baseSize * 1.5, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.15} />
      </mesh>
      {/* Main planet */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[baseSize, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={1.2}
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>
      {/* Ring for clusters */}
      {node.type === "cluster" && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[baseSize * 1.8, 0.015, 8, 64]} />
          <meshBasicMaterial color={color} transparent opacity={0.4} />
        </mesh>
      )}
      {/* Label */}
      <Billboard>
        <Text
          position={[0, baseSize + 0.2, 0]}
          fontSize={0.12}
          color="#cdd6f4"
          anchorX="center"
          anchorY="bottom"
          outlineColor="#000000"
          outlineWidth={0.01}
          font="/fonts/mono.woff"
        >
          {node.label.length > 18 ? node.label.slice(0, 18) + "..." : node.label}
        </Text>
        {node.runCount > 0 && (
          <Text
            position={[0, baseSize + 0.08, 0]}
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

// -- Edge beam --
function EdgeBeam({ edge, nodes }: { edge: GraphEdge; nodes: Map<string, GraphNode> }) {
  const source = nodes.get(edge.source);
  const target = nodes.get(edge.target);
  if (!source || !target) return null;

  const color = EDGE_COLORS[edge.type] || "#45475a";
  const opacity = Math.min(0.3 + edge.weight * 0.1, 0.9);

  const points = useMemo(() => [
    new THREE.Vector3(source.position.x, source.position.y, source.position.z),
    new THREE.Vector3(target.position.x, target.position.y, target.position.z),
  ], [source.position, target.position]);

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

// -- Orbiting particles for active clusters --
function OrbitalParticles({ node }: { node: GraphNode }) {
  const ref = useRef<THREE.Points>(null!);
  const count = Math.min(node.runCount * 5, 50);

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const radius = 0.4 + Math.random() * 0.3;
      arr[i * 3] = Math.cos(angle) * radius;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 0.2;
      arr[i * 3 + 2] = Math.sin(angle) * radius;
    }
    return arr;
  }, [count]);

  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y = state.clock.elapsedTime * 0.5;
      ref.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.2) * 0.1;
    }
  });

  if (count === 0) return null;

  return (
    <points ref={ref} position={[node.position.x, node.position.y, node.position.z]}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
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

// -- Scene --
function Scene({ graphState }: { graphState: GraphState }) {
  const nodeMap = useMemo(
    () => new Map(graphState.nodes.map((n) => [n.id, n])),
    [graphState.nodes]
  );

  const clusters = graphState.nodes.filter((n) => n.type === "cluster");

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.15} />
      <pointLight position={[0, 5, 0]} intensity={3} color="#cba6f7" />
      <pointLight position={[5, -3, 5]} intensity={2} color="#89b4fa" />
      <pointLight position={[-5, 2, -5]} intensity={1.5} color="#f38ba8" />

      {/* Starfield */}
      <Stars radius={50} depth={80} count={3000} factor={3} saturation={0.2} fade speed={0.5} />

      {/* Edges */}
      {graphState.edges.map((edge, i) => (
        <EdgeBeam key={`${edge.source}-${edge.target}-${i}`} edge={edge} nodes={nodeMap} />
      ))}

      {/* Nodes */}
      {graphState.nodes.map((node) => (
        <PlanetNode key={node.id} node={node} />
      ))}

      {/* Orbital particles for clusters with runs */}
      {clusters.filter((n) => n.runCount > 0).map((node) => (
        <OrbitalParticles key={`particles-${node.id}`} node={node} />
      ))}

      {/* Central star */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.2, 32, 32]} />
        <meshBasicMaterial color="#cba6f7" />
      </mesh>
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.5, 16, 16]} />
        <meshBasicMaterial color="#cba6f7" transparent opacity={0.15} />
      </mesh>
      <pointLight position={[0, 0, 0]} intensity={5} color="#cba6f7" distance={20} />

      {/* Post-processing - disabled for compatibility
      <EffectComposer>
        <Bloom luminanceThreshold={0.1} intensity={2.0} mipmapBlur />
      </EffectComposer>
      */}

      {/* Controls */}
      <OrbitControls
        enableDamping
        dampingFactor={0.05}
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

// -- Empty state --
function EmptyState() {
  return (
    <>
      <ambientLight intensity={0.1} />
      <Stars radius={50} depth={80} count={2000} factor={3} saturation={0.1} fade speed={0.3} />
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.15, 32, 32]} />
        <meshStandardMaterial color="#cba6f7" emissive="#cba6f7" emissiveIntensity={0.5} />
      </mesh>
      <Billboard position={[0, 0.5, 0]}>
        <Text fontSize={0.15} color="#6c7086" anchorX="center">
          Run a task to grow the knowledge universe...
        </Text>
      </Billboard>
      <OrbitControls autoRotate autoRotateSpeed={0.5} enableDamping />
    </>
  );
}

// -- Main export --
interface Props {
  graphState: GraphState | null;
}

export default function PlanetaryGraph({ graphState }: Props) {
  const hasData = graphState && graphState.nodes.length > 0;

  return (
    <div className="w-full h-full bg-crust rounded-lg overflow-hidden border border-surface0">
      <Canvas
        camera={{ position: [3, 2, 3], fov: 65, near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: false, preserveDrawingBuffer: true }}
        style={{ background: "#11111b" }}
      >
        {hasData ? <Scene graphState={graphState} /> : <EmptyState />}
      </Canvas>

      {/* HUD overlay */}
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
