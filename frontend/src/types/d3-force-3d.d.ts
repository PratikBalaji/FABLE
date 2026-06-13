/**
 * Minimal type shims for d3-force-3d (no @types package exists).
 * Only the API surface used by useForceLayout.ts is typed.
 */
declare module "d3-force-3d" {
  export interface SimNode {
    id?: string | number;
    x?: number;
    y?: number;
    z?: number;
    vx?: number;
    vy?: number;
    vz?: number;
    [key: string]: unknown;
  }

  export interface SimLink<N extends SimNode = SimNode> {
    source: number | string | N;
    target: number | string | N;
    [key: string]: unknown;
  }

  export interface ForceLink<N extends SimNode = SimNode, L extends SimLink<N> = SimLink<N>> {
    distance(d: number | ((link: L) => number)): this;
    strength(s: number | ((link: L) => number)): this;
    id(fn: (node: N) => string | number): this;
  }

  export interface ForceManyBody<N extends SimNode = SimNode> {
    strength(s: number | ((node: N) => number)): this;
  }

  export interface ForceCollide<N extends SimNode = SimNode> {
    radius(r: number | ((node: N) => number)): this;
  }

  export interface ForceCenter<N extends SimNode = SimNode> {
    strength(s: number): this;
  }

  export interface Simulation<N extends SimNode = SimNode> {
    force(name: string, f?: unknown): this;
    stop(): this;
    tick(n?: number): this;
  }

  export function forceSimulation<N extends SimNode = SimNode>(
    nodes?: N[],
    numDimensions?: number,
  ): Simulation<N>;

  export function forceManyBody<N extends SimNode = SimNode>(): ForceManyBody<N>;

  export function forceLink<N extends SimNode = SimNode, L extends SimLink<N> = SimLink<N>>(
    links?: L[],
  ): ForceLink<N, L>;

  export function forceCenter<N extends SimNode = SimNode>(
    x?: number, y?: number, z?: number,
  ): ForceCenter<N>;

  export function forceCollide<N extends SimNode = SimNode>(
    radius?: number | ((node: N) => number),
  ): ForceCollide<N>;
}
