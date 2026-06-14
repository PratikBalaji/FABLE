"use client";
import React, { useRef, useMemo, useEffect, useState, useCallback } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Stars, Text, Billboard, Line } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import { AnimatePresence, motion } from "framer-motion";
import type { GraphNode, GraphEdge, GraphState } from "@/lib/api";
import { useForceLayout, type PositionMap } from "./useForceLayout";

// ---------------------------------------------------------------------------
// P5a perf fixes preserved + P6-holographic:
//   • d3-force-3d layout replaces static backend coords (no clumping).
//   • Fresnel ShaderMaterial replaces solid emissive sphere.
//   • @react-three/postprocessing Bloom for holographic glow.
//   • Hover (highlight) + click (panel + camera focus) interaction.
//   • Single useFrame in Scene root (unchanged perf pattern).
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Colour palette
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

// ---------------------------------------------------------------------------
// Tunables
// ---------------------------------------------------------------------------
const TOP_K_NODES             = 30;
const MAX_PARTICLE_CLUSTERS   = 5;
const MAX_PARTICLES_PER_CLUSTER = 12;

// ---------------------------------------------------------------------------
// Module-scope geometries — single GPU upload.
// ---------------------------------------------------------------------------
const GEOM_SPHERE_MAIN = new THREE.SphereGeometry(1, 16, 16);
const GEOM_SPHERE_GLOW = new THREE.SphereGeometry(1, 12, 12);
const GEOM_RING        = new THREE.TorusGeometry(1, 0.015, 6, 32);

// ---------------------------------------------------------------------------
// Fresnel ShaderMaterial factory — holographic rim glow.
// ---------------------------------------------------------------------------
const FRESNEL_VERT = /* glsl */`
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
    vViewDir = normalize(-mvPos.xyz);
    gl_Position = projectionMatrix * mvPos;
  }
`;

const FRESNEL_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uRimPower;
  uniform float uCoreOpacity;
  uniform float uRimIntensity;
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    float facing = max(dot(vViewDir, vNormal), 0.0);
    float rim = pow(1.0 - facing, uRimPower) * uRimIntensity;
    float core = facing * uCoreOpacity;
    gl_FragColor = vec4(uColor, clamp(rim + core, 0.0, 1.0));
  }
`;

function makeFresnelMat(hexColor: string, opts?: { rimPower?: number; coreOpacity?: number; rimIntensity?: number }) {
  const color = new THREE.Color(hexColor);
  return new THREE.ShaderMaterial({
    vertexShader: FRESNEL_VERT,
    fragmentShader: FRESNEL_FRAG,
    uniforms: {
      uColor:       { value: color },
      uRimPower:    { value: opts?.rimPower    ?? 2.5 },
      uCoreOpacity: { value: opts?.coreOpacity ?? 0.12 },
      uRimIntensity:{ value: opts?.rimIntensity ?? 1.8 },
    },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.FrontSide,
  });
}

// ---------------------------------------------------------------------------
// PlanetNode
// ---------------------------------------------------------------------------
const RING_ROTATION: [number, number, number] = [Math.PI / 2, 0, 0];

interface PlanetNodeProps {
  node: GraphNode;
  pos: { x: number; y: number; z: number };
  isSelected: boolean;
  isHovered: boolean;
  registerRef: (id: string, mesh: THREE.Mesh | null, glow: THREE.Mesh | null, weight: number) => void;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}

function PlanetNode({ node, pos, isSelected, isHovered, registerRef, onSelect, onHover }: PlanetNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const color = TYPE_COLORS[node.type] || "#cdd6f4";

  // Smaller base size — holographic look reads better when nodes are small.
  const baseSize = useMemo(() => (
    node.type === "cluster"
      ? 0.25 + Math.min(node.weight, 10) * 0.05
      : 0.08 + Math.min(node.weight, 10) * 0.02
  ), [node.type, node.weight]);

  const highlightScale = isSelected ? 1.6 : isHovered ? 1.35 : 1.0;

  const position = useMemo<[number, number, number]>(
    () => [pos.x, pos.y, pos.z],
    [pos.x, pos.y, pos.z],
  );

  const labelOffset = useMemo<[number, number, number]>(
    () => [0, baseSize * highlightScale + 0.18, 0],
    [baseSize, highlightScale],
  );

  // Fresnel material — created once per mount.
  const fresnelMat = useMemo(
    () => makeFresnelMat(color, {
      rimPower:     isSelected ? 1.8 : 2.5,
      coreOpacity:  isSelected ? 0.22 : 0.12,
      rimIntensity: isSelected ? 2.8 : isHovered ? 2.2 : 1.8,
    }),
    // Recreate when selection/hover changes to update uniforms cheaply.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [color, isSelected, isHovered],
  );

  // Bright inner core (tiny solid sphere for the "nucleus").
  const coreMat = useMemo(() => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 }), [color]);

  useEffect(() => {
    registerRef(node.id, meshRef.current, glowRef.current, node.weight);
    return () => registerRef(node.id, null, null, node.weight);
  }, [node.id, node.weight, registerRef]);

  return (
    <group
      position={position}
      onPointerOver={(e) => { e.stopPropagation(); onHover(node.id); document.body.style.cursor = "pointer"; }}
      onPointerOut={(e)  => { e.stopPropagation(); onHover(null);    document.body.style.cursor = "default"; }}
      onClick={(e) => { e.stopPropagation(); onSelect(node.id); }}
    >
      {/* Fresnel hologram shell */}
      <mesh ref={meshRef} geometry={GEOM_SPHERE_MAIN} scale={baseSize * highlightScale} material={fresnelMat} />

      {/* Tiny bright nucleus */}
      <mesh geometry={GEOM_SPHERE_MAIN} scale={baseSize * highlightScale * 0.28} material={coreMat} />

      {/* Outer glow haze */}
      <mesh ref={glowRef} geometry={GEOM_SPHERE_GLOW} scale={baseSize * highlightScale * 2.2}>
        <meshBasicMaterial color={color} transparent opacity={0.04} depthWrite={false} />
      </mesh>

      {/* Cluster ring */}
      {node.type === "cluster" && (
        <mesh geometry={GEOM_RING} rotation={RING_ROTATION} scale={baseSize * highlightScale * 2.0}>
          <meshBasicMaterial color={color} transparent opacity={isSelected ? 0.7 : 0.35} depthWrite={false} />
        </mesh>
      )}

      <Billboard>
        <Text
          position={labelOffset}
          fontSize={0.10}
          color={isSelected ? "#ffffff" : isHovered ? "#ede9fe" : "#cdd6f4"}
          anchorX="center"
          anchorY="bottom"
          outlineColor="#000000"
          outlineWidth={0.008}
        >
          {node.label.length > 20 ? node.label.slice(0, 20) + "…" : node.label}
        </Text>
      </Billboard>
    </group>
  );
}

// ---------------------------------------------------------------------------
// EdgeBeam
// ---------------------------------------------------------------------------
function EdgeBeam({ edge, posMap }: { edge: GraphEdge; posMap: PositionMap }) {
  const sp = posMap.get(edge.source);
  const tp = posMap.get(edge.target);

  const points = useMemo(() => {
    if (!sp || !tp) return null;
    return [
      new THREE.Vector3(sp.x, sp.y, sp.z),
      new THREE.Vector3(tp.x, tp.y, tp.z),
    ];
  }, [sp?.x, sp?.y, sp?.z, tp?.x, tp?.y, tp?.z]);

  if (!points) return null;

  const color   = EDGE_COLORS[edge.type] || "#45475a";
  const opacity = Math.min(0.15 + edge.weight * 0.07, 0.55);

  return (
    <Line
      points={points}
      color={color}
      lineWidth={Math.min(0.3 + edge.weight * 0.15, 1.5)}
      transparent
      opacity={opacity}
    />
  );
}

// ---------------------------------------------------------------------------
// OrbitalParticles
// ---------------------------------------------------------------------------
function OrbitalParticles({ node, pos }: { node: GraphNode; pos: { x: number; y: number; z: number } }) {
  const ref = useRef<THREE.Points>(null);
  const count = Math.min(node.runCount * 2, MAX_PARTICLES_PER_CLUSTER);

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle  = (i / count) * Math.PI * 2;
      const radius = 0.4 + (i % 7) / 30;
      arr[i * 3]     = Math.cos(angle) * radius;
      arr[i * 3 + 1] = (((i * 37) % 100) / 100 - 0.5) * 0.2;
      arr[i * 3 + 2] = Math.sin(angle) * radius;
    }
    return arr;
  }, [count]);

  const position = useMemo<[number, number, number]>(
    () => [pos.x, pos.y, pos.z],
    [pos.x, pos.y, pos.z],
  );

  useFrame((state) => {
    if (ref.current) ref.current.rotation.y = state.clock.elapsedTime * 0.5;
  });

  if (count === 0) return null;

  return (
    <points ref={ref} position={position}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.015}
        color={TYPE_COLORS[node.type] || "#cdd6f4"}
        transparent
        opacity={0.5}
        sizeAttenuation
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// CameraFocus — lerps camera + OrbitControls target toward selected node.
// ---------------------------------------------------------------------------
interface CameraFocusProps {
  targetPos: THREE.Vector3 | null;
  controlsRef: React.RefObject<{ target: THREE.Vector3; autoRotate: boolean }>;
}

function CameraFocus({ targetPos, controlsRef }: CameraFocusProps) {
  const { camera } = useThree();
  const lerpTarget = useRef(new THREE.Vector3());
  const lerpCam    = useRef(new THREE.Vector3());
  const active     = useRef(false);

  useEffect(() => {
    if (targetPos) {
      lerpTarget.current.copy(targetPos);
      // Place camera offset from node.
      lerpCam.current.copy(targetPos).add(new THREE.Vector3(3, 2, 3));
      active.current = true;
      if (controlsRef.current) controlsRef.current.autoRotate = false;
    } else {
      active.current = false;
      if (controlsRef.current) controlsRef.current.autoRotate = true;
    }
  }, [targetPos, controlsRef]);

  useFrame(() => {
    if (!active.current || !controlsRef.current) return;
    camera.position.lerp(lerpCam.current, 0.05);
    controlsRef.current.target.lerp(lerpTarget.current, 0.05);
  });

  return null;
}

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------
interface NodeAnim {
  mesh: THREE.Mesh | null;
  glow: THREE.Mesh | null;
  weight: number;
}

interface SceneProps {
  graphState: GraphState;
  selectedNodeId: string | null;
  hoveredNodeId:  string | null;
  onSelect: (id: string | null) => void;
  onHover:  (id: string | null) => void;
  controlsRef: React.RefObject<{ target: THREE.Vector3; autoRotate: boolean }>;
}

function Scene({ graphState, selectedNodeId, hoveredNodeId, onSelect, onHover, controlsRef }: SceneProps) {
  const topNodes = useMemo(() => {
    const sorted = [...graphState.nodes].sort((a, b) => b.weight - a.weight);
    return sorted.slice(0, TOP_K_NODES);
  }, [graphState.nodes]);

  const nodeMap = useMemo(() => new Map(topNodes.map((n) => [n.id, n])), [topNodes]);

  const visibleEdges = useMemo(
    () => graphState.edges.filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target)),
    [graphState.edges, nodeMap],
  );

  const activeClusters = useMemo(
    () => topNodes.filter((n) => n.type === "cluster" && n.runCount > 0).slice(0, MAX_PARTICLE_CLUSTERS),
    [topNodes],
  );

  // Force layout — positions spread via d3-force-3d.
  const posMap = useForceLayout(topNodes, visibleEdges);

  // Camera focus target.
  const selectedPos = useMemo<THREE.Vector3 | null>(() => {
    if (!selectedNodeId) return null;
    const p = posMap.get(selectedNodeId);
    return p ? new THREE.Vector3(p.x, p.y, p.z) : null;
  }, [selectedNodeId, posMap]);

  // Animation registry.
  const animRefs = useRef<Map<string, NodeAnim>>(new Map());
  const registerRef = useMemo(() => (
    (id: string, mesh: THREE.Mesh | null, glow: THREE.Mesh | null, weight: number) => {
      if (!mesh && !glow) animRefs.current.delete(id);
      else animRefs.current.set(id, { mesh, glow, weight });
    }
  ), []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    animRefs.current.forEach((rec) => {
      if (rec.mesh) {
        rec.mesh.rotation.y = t * 0.25;
        const pulse = 1 + Math.sin(t * 2 + rec.weight) * 0.04;
        rec.mesh.scale.setScalar(pulse * (rec.mesh.userData.baseScale ?? 1));
      }
      if (rec.glow) {
        const gPulse = 1.0 + Math.sin(t * 1.2) * 0.12;
        rec.glow.scale.setScalar(gPulse * (rec.glow.userData.baseScale ?? 1));
      }
    });
  });

  const hiddenCount = graphState.nodes.length - topNodes.length;

  return (
    <>
      <ambientLight intensity={0.08} />
      <pointLight position={[0,  8, 0]}   intensity={2}   color="#cba6f7" />
      <pointLight position={[8, -4, 8]}   intensity={1.5} color="#89b4fa" />
      <pointLight position={[-8, 3, -8]}  intensity={1}   color="#f38ba8" />

      <Stars radius={120} depth={120} count={500} factor={4} saturation={0.15} fade speed={0.3} />

      {/* Edges */}
      {visibleEdges.map((edge, i) => (
        <EdgeBeam key={`${edge.source}-${edge.target}-${i}`} edge={edge} posMap={posMap} />
      ))}

      {/* Nodes */}
      {topNodes.map((node) => {
        const pos = posMap.get(node.id) ?? { x: 0, y: 0, z: 0 };
        return (
          <PlanetNode
            key={node.id}
            node={node}
            pos={pos}
            isSelected={node.id === selectedNodeId}
            isHovered={node.id === hoveredNodeId}
            registerRef={registerRef}
            onSelect={(id) => onSelect(selectedNodeId === id ? null : id)}
            onHover={onHover}
          />
        );
      })}

      {/* Orbital particles */}
      {activeClusters.map((node) => {
        const pos = posMap.get(node.id) ?? { x: 0, y: 0, z: 0 };
        return <OrbitalParticles key={`particles-${node.id}`} node={node} pos={pos} />;
      })}

      {/* Central star */}
      <mesh position={[0, 0, 0]} geometry={GEOM_SPHERE_MAIN} scale={0.15}>
        <meshBasicMaterial color="#cba6f7" />
      </mesh>
      <mesh position={[0, 0, 0]} geometry={GEOM_SPHERE_GLOW} scale={0.4}>
        <meshBasicMaterial color="#cba6f7" transparent opacity={0.12} depthWrite={false} />
      </mesh>
      <pointLight position={[0, 0, 0]} intensity={4} color="#cba6f7" distance={30} />

      {hiddenCount > 0 && (
        <Billboard position={[0, -4, 0]}>
          <Text fontSize={0.1} color="#6c7086" anchorX="center">
            {`+${hiddenCount} more nodes hidden (top ${TOP_K_NODES} shown)`}
          </Text>
        </Billboard>
      )}

      <CameraFocus targetPos={selectedPos} controlsRef={controlsRef} />

      {/* Bloom post-processing — holographic glow */}
      <EffectComposer>
        <Bloom
          luminanceThreshold={0.15}
          luminanceSmoothing={0.9}
          intensity={1.4}
          mipmapBlur
          levels={8}
        />
      </EffectComposer>

      <OrbitControls
        ref={controlsRef as React.RefObject<any>}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
        minDistance={3}
        maxDistance={80}
        autoRotate={!selectedNodeId}
        autoRotateSpeed={0.25}
        onClick={() => onSelect(null)}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------
function EmptyState() {
  return (
    <>
      <ambientLight intensity={0.08} />
      <Stars radius={120} depth={120} count={300} factor={4} saturation={0.1} fade speed={0.25} />
      <mesh position={[0, 0, 0]} geometry={GEOM_SPHERE_MAIN} scale={0.12}>
        <meshStandardMaterial color="#cba6f7" emissive="#cba6f7" emissiveIntensity={0.6} />
      </mesh>
      <Billboard position={[0, 0.5, 0]}>
        <Text fontSize={0.14} color="#6c7086" anchorX="center">
          Run a task to grow the knowledge universe…
        </Text>
      </Billboard>
      <EffectComposer>
        <Bloom luminanceThreshold={0.2} intensity={1.0} mipmapBlur levels={6} />
      </EffectComposer>
      <OrbitControls autoRotate autoRotateSpeed={0.4} enableDamping dampingFactor={0.08} />
    </>
  );
}

// ---------------------------------------------------------------------------
// NodeDetailPanel — framer-motion overlay, rendered in HTML (not Canvas).
// ---------------------------------------------------------------------------
const TYPE_LABELS: Record<string, string> = {
  cluster: "Knowledge Cluster",
  concept: "Concept",
  model:   "Model",
  domain:  "Domain",
};

interface NodeDetailPanelProps {
  node: GraphNode | null;
  edgeCount: number;
  onClose: () => void;
}

function NodeDetailPanel({ node, edgeCount, onClose }: NodeDetailPanelProps) {
  return (
    <AnimatePresence>
      {node && (
        <motion.div
          key={node.id}
          initial={{ opacity: 0, x: 32 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 32 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="absolute top-3 right-3 w-64 bg-crust/85 backdrop-blur-md border border-surface0 rounded-xl px-4 py-4 space-y-3 shadow-2xl z-10"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <p className="text-xs text-subtext font-mono uppercase tracking-widest mb-0.5">
                {TYPE_LABELS[node.type] ?? node.type}
              </p>
              <h3 className="text-sm font-semibold text-text truncate" title={node.label}>
                {node.label}
              </h3>
            </div>
            <button
              onClick={onClose}
              className="text-overlay1 hover:text-text transition-colors shrink-0 mt-0.5 text-xs"
              aria-label="Close panel"
            >
              ✕
            </button>
          </div>

          {/* Colour badge */}
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ background: TYPE_COLORS[node.type] ?? "#cdd6f4", boxShadow: `0 0 6px ${TYPE_COLORS[node.type] ?? "#cdd6f4"}` }}
            />
            <span className="text-xs text-subtext font-mono">{TYPE_COLORS[node.type] ?? "#cdd6f4"}</span>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="bg-surface0/60 rounded-lg px-3 py-2">
              <p className="text-overlay1 text-[10px] uppercase tracking-wider mb-0.5">Weight</p>
              <p className="text-accent font-semibold">{node.weight.toFixed(2)}</p>
            </div>
            <div className="bg-surface0/60 rounded-lg px-3 py-2">
              <p className="text-overlay1 text-[10px] uppercase tracking-wider mb-0.5">Runs</p>
              <p className="text-accent font-semibold">{node.runCount}</p>
            </div>
            <div className="bg-surface0/60 rounded-lg px-3 py-2 col-span-2">
              <p className="text-overlay1 text-[10px] uppercase tracking-wider mb-0.5">Connections</p>
              <p className="text-accent font-semibold">{edgeCount}</p>
            </div>
          </div>

          {/* Node ID */}
          <p className="text-[10px] text-overlay0 font-mono truncate" title={node.id}>
            id: {node.id}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------
interface Props {
  graphState: GraphState | null;
}

export default function PlanetaryGraph({ graphState }: Props) {
  const hasData = graphState && graphState.nodes.length > 0;

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId,  setHoveredNodeId]  = useState<string | null>(null);

  // Typed as any to avoid the complex drei ref typing; the shape we use is simple.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const controlsRef = useRef<any>(null);

  const selectedNode = useMemo(
    () => graphState?.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [graphState, selectedNodeId],
  );

  const selectedEdgeCount = useMemo(
    () => graphState?.edges.filter(
      (e) => e.source === selectedNodeId || e.target === selectedNodeId,
    ).length ?? 0,
    [graphState, selectedNodeId],
  );

  const handleSelect = useCallback((id: string | null) => setSelectedNodeId(id), []);
  const handleHover  = useCallback((id: string | null) => setHoveredNodeId(id),  []);

  // Deselect on click outside.
  const handleCanvasClick = useCallback(() => {
    if (hoveredNodeId === null) setSelectedNodeId(null);
  }, [hoveredNodeId]);

  useEffect(() => {
    return () => {
      GEOM_SPHERE_MAIN.dispose();
      GEOM_SPHERE_GLOW.dispose();
      GEOM_RING.dispose();
      document.body.style.cursor = "default";
    };
  }, []);

  return (
    <div className="w-full h-full bg-crust rounded-lg overflow-hidden border border-surface0 relative">
      <Canvas
        camera={{ position: [0, 8, 20], fov: 55, near: 0.1, far: 300 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
        style={{ background: "#0a0a12" }}
        onClick={handleCanvasClick}
      >
        {hasData
          ? <Scene
              graphState={graphState}
              selectedNodeId={selectedNodeId}
              hoveredNodeId={hoveredNodeId}
              onSelect={handleSelect}
              onHover={handleHover}
              controlsRef={controlsRef}
            />
          : <EmptyState />}
      </Canvas>

      {/* Stats overlay (bottom-left) */}
      {graphState?.stats && (
        <div className="absolute bottom-3 left-3 bg-crust/80 backdrop-blur border border-surface0 rounded px-3 py-2 text-xs font-mono space-y-0.5 pointer-events-none">
          <div className="text-accent font-bold">KNOWLEDGE ENGINE</div>
          <div className="text-subtext">{graphState.stats.totalRuns} runs processed</div>
          <div className="text-subtext">{graphState.stats.clusters} planets · {graphState.stats.concepts} concepts</div>
          <div className="text-subtext">{graphState.stats.totalEdges} connections</div>
        </div>
      )}

      {/* Selection hint (bottom-center) */}
      {hasData && !selectedNodeId && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 pointer-events-none">
          <p className="text-[10px] text-overlay0 font-mono">click a node to inspect</p>
        </div>
      )}

      {/* Node detail panel (top-right) */}
      <NodeDetailPanel
        node={selectedNode}
        edgeCount={selectedEdgeCount}
        onClose={() => setSelectedNodeId(null)}
      />
    </div>
  );
}
