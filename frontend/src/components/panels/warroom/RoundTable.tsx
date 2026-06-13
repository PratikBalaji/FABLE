"use client";
import React, { useMemo } from "react";
import { AgentCharacter } from "./AgentCharacter";
import { SpeechBubble } from "./SpeechBubble";
import type { AgentMessage } from "@/lib/api";

interface RoleMeta {
  label: string;
  color: string;
}

interface SeatConfig {
  role: string;
  meta: RoleMeta;
  /** Pixel coords relative to container */
  cx: number;
  cy: number;
}

interface RoundTableProps {
  agentOrder: string[];
  getRoleMeta: (role: string) => RoleMeta;
  activeRole: string | null;
  doneRoles: Set<string>;
  /** Latest message for the currently active role (for the speech bubble) */
  activeMessage: AgentMessage | null;
  onCharacterClick: (role: string) => void;
  /** Container size in px */
  width?: number;
  height?: number;
}

/**
 * SVG round table with Among-Us characters evenly seated around an ellipse.
 * A speech bubble pops above the currently active character.
 */
export function RoundTable({
  agentOrder,
  getRoleMeta,
  activeRole,
  doneRoles,
  activeMessage,
  onCharacterClick,
  width = 460,
  height = 310,
}: RoundTableProps) {
  const cx = width / 2;
  const cy = height / 2;
  const rx = width * 0.36;
  const ry = height * 0.34;

  const seats = useMemo<SeatConfig[]>(() => {
    const n = agentOrder.length;
    return agentOrder.map((role, i) => {
      // Start at top (−π/2) and go clockwise
      const angle = -Math.PI / 2 + (i / n) * 2 * Math.PI;
      return {
        role,
        meta: getRoleMeta(role),
        cx: cx + rx * Math.cos(angle),
        cy: cy + ry * Math.sin(angle),
      };
    });
  }, [agentOrder, getRoleMeta, cx, cy, rx, ry]);

  // Find the seat of the active speaker for bubble positioning
  const activeSeat = seats.find((s) => s.role === activeRole);

  return (
    <div className="relative select-none" style={{ width, height }}>
      {/* SVG for the table */}
      <svg
        width={width}
        height={height}
        className="absolute inset-0 pointer-events-none"
        style={{ zIndex: 0 }}
      >
        {/* Table ellipse */}
        <ellipse
          cx={cx} cy={cy}
          rx={rx * 0.62} ry={ry * 0.58}
          fill="rgba(30,30,46,0.85)"
          stroke="rgba(203,166,247,0.18)"
          strokeWidth="1.5"
        />
        {/* Table glow */}
        <ellipse
          cx={cx} cy={cy}
          rx={rx * 0.62} ry={ry * 0.58}
          fill="none"
          stroke="rgba(203,166,247,0.07)"
          strokeWidth="6"
          filter="url(#tableGlow)"
        />
        <defs>
          <filter id="tableGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Seat connectors (thin lines from centre to each seat) */}
        {seats.map(({ role, cx: scx, cy: scy, meta }) => (
          <line
            key={role}
            x1={cx} y1={cy}
            x2={scx} y2={scy}
            stroke={`${meta.color}18`}
            strokeWidth="1"
            strokeDasharray="3 4"
          />
        ))}

        {/* Center sigil */}
        <circle cx={cx} cy={cy} r={8} fill="rgba(203,166,247,0.15)" stroke="rgba(203,166,247,0.4)" strokeWidth="1" />
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="8" fill="rgba(203,166,247,0.7)">⚡</text>
      </svg>

      {/* Characters */}
      {seats.map(({ role, meta, cx: scx, cy: scy }) => (
        <div
          key={role}
          className="absolute"
          style={{
            left: scx - 22,  // half of character width 44
            top: scy - 26,   // half of character height 52
            zIndex: 1,
          }}
        >
          <AgentCharacter
            color={meta.color}
            label={meta.label}
            isActive={activeRole === role}
            isDone={doneRoles.has(role) && activeRole !== role}
            onClick={() => onCharacterClick(role)}
          />
        </div>
      ))}

      {/* Speech bubble pinned to active seat */}
      {activeSeat && (
        <SpeechBubble
          msg={activeMessage}
          color={activeSeat.meta.color}
          x={activeSeat.cx}
          y={activeSeat.cy - 30}
        />
      )}
    </div>
  );
}
