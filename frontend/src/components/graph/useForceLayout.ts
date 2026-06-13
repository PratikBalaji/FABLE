/**
 * useForceLayout — 3-D force-directed layout for the knowledge graph.
 *
 * Runs a synchronous d3-force-3d simulation (300 ticks) and returns a stable
 * Map<nodeId, {x,y,z}> so the graph stays spread out without per-frame cost.
 * Re-runs only when the node/edge fingerprint changes.
 *
 * Note: PlanetaryGraph is imported with `{ ssr: false }` via next/dynamic, so
 * this file is never executed on the server — ESM d3-force-3d imports are safe.
 */
import { useMemo } from "react";
// d3-force-3d is ESM-only; this file is client-only (dynamic import in page).
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  forceCollide,
} from "d3-force-3d";
import type { GraphNode, GraphEdge } from "@/lib/api";

export type PositionMap = Map<string, { x: number; y: number; z: number }>;

/**
 * Returns a Map of computed 3-D positions keyed by node id.
 * Positions are scaled by SPREAD after simulation for visual separation.
 */
export function useForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
): PositionMap {
  // Fingerprint: recompute only when nodes or edges change structurally.
  const nodeIds  = nodes.map((n) => n.id).join(",");
  const edgeCount = edges.length;

  return useMemo<PositionMap>(() => {
    if (nodes.length === 0) return new Map();

    // d3-force-3d mutates nodes in place, adding x / y / z.
    // Work on shallow copies to avoid polluting the original GraphNode objects.
    const simNodes = nodes.map((n) => ({ id: n.id, weight: n.weight }));
    const idIndex  = new Map(simNodes.map((n, i) => [n.id, i]));

    const simLinks = edges
      .filter((e) => idIndex.has(e.source) && idIndex.has(e.target))
      .map((e) => ({
        source: idIndex.get(e.source)!,
        target: idIndex.get(e.target)!,
        weight: e.weight,
      }));

    const nodeRadius = (n: { weight: number }) =>
      0.25 + Math.min(n.weight, 10) * 0.04;

    const sim = forceSimulation(simNodes, 3 /* numDimensions */)
      .force("charge", forceManyBody().strength(-180))
      .force(
        "link",
        forceLink(simLinks)
          .distance((d: { weight: number }) => 6 + d.weight * 0.5)
          .strength(0.6),
      )
      .force(
        "collide",
        forceCollide((d: { weight: number }) => nodeRadius(d) * 3.5),
      )
      .force("center", forceCenter(0, 0, 0).strength(0.04))
      .stop();

    sim.tick(300);

    const SPREAD = 1.8;
    const out: PositionMap = new Map();
    (simNodes as Array<{ id: string; x?: number; y?: number; z?: number }>).forEach((n) => {
      out.set(n.id, {
        x: (n.x ?? 0) * SPREAD,
        y: (n.y ?? 0) * SPREAD,
        z: (n.z ?? 0) * SPREAD,
      });
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeIds, edgeCount]);
}
