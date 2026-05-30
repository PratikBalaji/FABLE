"use client";
import React from "react";
import type { AgentMessage } from "@/lib/api";

const ROLE_STYLES: Record<string, { border: string; label: string; badge: string }> = {
  analyst:     { border: "border-blue",    label: "Analyst",     badge: "bg-blue/20 text-blue" },
  critic:      { border: "border-red",     label: "Critic",      badge: "bg-red/20 text-red" },
  synthesizer: { border: "border-green",   label: "Synthesizer", badge: "bg-green/20 text-green" },
};

function MessageCard({ msg }: { msg: AgentMessage }) {
  const style = ROLE_STYLES[msg.role] ?? {
    border: "border-surface1",
    label: msg.role,
    badge: "bg-surface0 text-subtext",
  };

  return (
    <div className={`rounded-lg border ${style.border} bg-mantle p-4 mb-3 space-y-2`}>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-mono px-2 py-0.5 rounded ${style.badge}`}>
          {style.label.toUpperCase()}
        </span>
        <span className="text-xs text-overlay font-mono">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <p className="text-text text-sm font-mono whitespace-pre-wrap leading-relaxed">
        {msg.content}
      </p>
    </div>
  );
}

interface Props {
  messages: AgentMessage[];
  isLoading?: boolean;
}

export default function AgentThread({ messages, isLoading }: Props) {
  return (
    <div className="h-full overflow-y-auto pr-1 space-y-1">
      {messages.length === 0 && !isLoading && (
        <p className="text-overlay text-sm font-mono text-center mt-16">
          Submit a task to start the agent collaboration...
        </p>
      )}
      {messages.map((m) => (
        <MessageCard key={m.message_id} msg={m} />
      ))}
      {isLoading && (
        <div className="rounded-lg border border-surface0 bg-mantle p-4 animate-pulse">
          <div className="h-3 bg-surface0 rounded w-24 mb-2" />
          <div className="h-2 bg-surface0 rounded w-full mb-1" />
          <div className="h-2 bg-surface0 rounded w-3/4" />
        </div>
      )}
    </div>
  );
}
