"use client";
import React from "react";
import { motion } from "framer-motion";

/** Glass card wrapper for bento cells. `span` = grid column span (1 or 2). */
export function BentoCard({
  title, subtitle, span = 1, id, children,
}: {
  title?: string; subtitle?: string; span?: 1 | 2; id?: string; children: React.ReactNode;
}) {
  return (
    <motion.section
      id={id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32 }}
      className="glass hover-lift p-5"
      style={{ gridColumn: `span ${span}` }}
    >
      {title && (
        <div className="mb-3">
          <h2 className="text-[13px] font-semibold tracking-wide" style={{ color: "#cba6f7" }}>{title}</h2>
          {subtitle && <p className="text-[11px] mt-0.5" style={{ color: "#6b6b8a" }}>{subtitle}</p>}
        </div>
      )}
      {children}
    </motion.section>
  );
}

/** Responsive bento grid. */
export function BentoGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
      {children}
    </div>
  );
}
