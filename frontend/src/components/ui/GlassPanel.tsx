import React from "react";
import { cn } from "./cn";

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
}

export function GlassPanel({ children, className }: GlassPanelProps) {
  return (
    <div className={cn("glass", className)}>
      {children}
    </div>
  );
}
