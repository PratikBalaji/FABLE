"use client";
import React from "react";
import { ArrowLeft, LayoutGrid, Layers, DollarSign, Activity, Database, UploadCloud, ShieldCheck, KeyRound, Gauge } from "lucide-react";

export interface NavSection {
  id: string;
  label: string;
  icon: React.ReactNode;
}

export const NAV_SECTIONS: NavSection[] = [
  { id: "overview", label: "Overview", icon: <LayoutGrid size={15} /> },
  { id: "modes",    label: "Modes",    icon: <Layers size={15} /> },
  { id: "cost",     label: "Cost",     icon: <DollarSign size={15} /> },
  { id: "traces",   label: "Traces",   icon: <Activity size={15} /> },
  { id: "dataset",  label: "Dataset",  icon: <Database size={15} /> },
  { id: "privacy",  label: "Privacy",  icon: <ShieldCheck size={15} /> },
  { id: "limits",   label: "Limits",   icon: <Gauge size={15} /> },
];

interface DashSidebarProps {
  active: string;
  onNavigate: (id: string) => void;
  onExport: () => void;
  onByok: () => void;
  children?: React.ReactNode;   // FilterRail slot
}

export function DashSidebar({ active, onNavigate, onExport, onByok, children }: DashSidebarProps) {
  return (
    <aside className="glass-panel flex flex-col h-full px-4 py-5" style={{ borderRadius: 0 }}>
      <a href="/" className="flex items-center gap-2 mb-1 text-[13px] transition-colors hover:opacity-80"
         style={{ color: "#6b6b8a" }}>
        <ArrowLeft size={14} /> FABLE
      </a>
      <div className="mb-6">
        <div className="font-bold text-[17px] tracking-wide" style={{ color: "#cba6f7", textShadow: "0 0 24px rgba(203,166,247,0.5)" }}>
          Dashboard
        </div>
        <div className="text-[10px]" style={{ color: "#45455d" }}>60 Preliminary Eval Cases</div>
      </div>

      <nav className="flex flex-col gap-1 mb-6">
        {NAV_SECTIONS.map((s) => (
          <button key={s.id} onClick={() => onNavigate(s.id)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] transition-all duration-150 text-left"
                  style={{
                    background: active === s.id ? "rgba(203,166,247,0.12)" : "transparent",
                    color: active === s.id ? "#e8e8f5" : "#6b6b8a",
                    boxShadow: active === s.id ? "0 0 0 1px rgba(203,166,247,0.25)" : "none",
                  }}>
            {s.icon} {s.label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto -mx-1 px-1">
        {children}
      </div>

      <button onClick={onByok}
              className="mt-4 flex items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] font-medium transition-all glass-ghost"
              style={{ color: "#cdd6f4" }}>
        <KeyRound size={15} /> Your API Key
      </button>
      <button onClick={onExport}
              className="mt-2 flex items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] font-semibold transition-all hover-lift"
              style={{ background: "#cba6f7", color: "#0d0d1a" }}>
        <UploadCloud size={15} /> Export to Kaggle
      </button>
    </aside>
  );
}
