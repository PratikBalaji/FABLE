"use client";
import React, { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, X, FileText, File, ArrowUp } from "lucide-react";
import { cn } from "@/components/ui/cn";

// ─── File chip ────────────────────────────────────────────────────────────────
function FileChip({ name, onRemove }: { name: string; onRemove: () => void }) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const isDoc = ["pdf", "docx", "doc"].includes(ext);
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.85 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[10px] font-sans max-w-[180px]"
      style={{
        background: "rgba(12,12,28,0.88)",
        backdropFilter: "blur(20px)",
        boxShadow: "0 0 0 1px rgba(180,160,232,0.10)",
        color: "#9494aa",
      }}
    >
      {isDoc
        ? <FileText size={10} style={{ color: "#cba6f7", flexShrink: 0 }} />
        : <File     size={10} style={{ color: "#6b6b8a", flexShrink: 0 }} />
      }
      <span className="truncate">{name}</span>
      <button
        onClick={onRemove}
        className="ml-0.5 transition-colors"
        style={{ color: "#6b6b8a" }}
        onMouseEnter={e => (e.currentTarget.style.color = "#f38ba8")}
        onMouseLeave={e => (e.currentTarget.style.color = "#6b6b8a")}
        aria-label={`Remove ${name}`}
      >
        <X size={9} />
      </button>
    </motion.span>
  );
}

// ─── Composer ────────────────────────────────────────────────────────────────
export interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  isLoading: boolean;
  mode: "standard" | "adversarial";
  uploadedFiles: File[];
  uploadStatus: string | null;
  onFilesChange: (files: FileList | null) => void;
  onRemoveFile: (idx: number) => void;
  error: string | null;
}

/**
 * Spotlight/iMessage-style floating composer.
 * Expands vertically on focus, contracts when blurred and empty.
 * No rigid borders — depth via shadow only.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  isLoading,
  mode,
  uploadedFiles,
  uploadStatus,
  onFilesChange,
  onRemoveFile,
  error,
}: ComposerProps) {
  const [focused, setFocused] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit(e as unknown as React.FormEvent);
    }
  };

  const hasContent = value.trim().length > 0;
  const expanded = focused || hasContent || uploadedFiles.length > 0;

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    onFilesChange(e.dataTransfer.files);
  };

  return (
    <motion.div
      layout
      className="w-full max-w-2xl mx-auto"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      {/* Error toast */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 340, damping: 28 }}
            className="mb-2 px-4 py-2.5 rounded-xl text-[11px] font-sans text-center"
            style={{
              background: "rgba(243,139,168,0.08)",
              boxShadow: "0 0 0 1px rgba(243,139,168,0.18)",
              color: "#f38ba8",
            }}
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Upload status */}
      <AnimatePresence>
        {uploadStatus && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mb-1.5 text-[10px] font-sans text-center"
            style={{ color: "#9494aa" }}
          >
            {uploadStatus}
          </motion.p>
        )}
      </AnimatePresence>

      {/* File chips */}
      <AnimatePresence>
        {uploadedFiles.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="flex flex-wrap justify-center gap-1.5 mb-2"
          >
            {uploadedFiles.map((f, i) => (
              <FileChip key={`${f.name}-${i}`} name={f.name} onRemove={() => onRemoveFile(i)} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main composer pill */}
      <motion.div
        layout
        className={cn(
          "relative flex items-end gap-2 px-4 transition-all duration-300",
          expanded ? "py-3" : "py-2.5"
        )}
        style={{
          background: "rgba(10,10,22,0.88)",
          backdropFilter: "blur(40px) saturate(1.6)",
          WebkitBackdropFilter: "blur(40px) saturate(1.6)",
          borderRadius: 28,
          boxShadow: focused
            ? "0 0 0 1px rgba(203,166,247,0.28), 0 12px 60px rgba(0,0,0,0.72), 0 0 40px rgba(140,80,220,0.08) inset"
            : "0 0 0 1px rgba(180,160,232,0.09), 0 8px 48px rgba(0,0,0,0.65)",
        }}
      >
        {/* Upload icon button */}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={isLoading}
          className="flex-none mb-0.5 transition-opacity"
          style={{ color: "#6b6b8a", opacity: isLoading ? 0.35 : 1 }}
          onMouseEnter={e => !isLoading && (e.currentTarget.style.color = "#cba6f7")}
          onMouseLeave={e => (e.currentTarget.style.color = "#6b6b8a")}
          aria-label="Attach document"
        >
          <Upload size={16} />
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.md,.markdown,.txt,.csv,.json"
          className="hidden"
          onChange={(e) => onFilesChange(e.target.files)}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={
            mode === "adversarial"
              ? "Ask something challenging — 6 agents will deliberate…"
              : "Ask anything — code, research, creative, analysis…"
          }
          rows={expanded ? 3 : 1}
          disabled={isLoading}
          className="flex-1 resize-none bg-transparent text-[13px] font-sans leading-relaxed focus:outline-none placeholder:text-[#3f3f5a] transition-all duration-300"
          style={{
            color: "#cdd6f4",
            minHeight: expanded ? 68 : 22,
            maxHeight: 160,
          }}
        />

        {/* Submit button */}
        <motion.button
          type="button"
          onClick={onSubmit as unknown as React.MouseEventHandler}
          disabled={isLoading || !hasContent}
          whileTap={{ scale: 0.92 }}
          whileHover={{ scale: hasContent && !isLoading ? 1.06 : 1 }}
          className="flex-none mb-0.5 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 disabled:opacity-25 disabled:cursor-not-allowed"
          style={{
            background: hasContent && !isLoading
              ? mode === "adversarial"
                ? "linear-gradient(135deg, #9b60d0, #7d44b0)"
                : "linear-gradient(135deg, #cba6f7, #9b60d0)"
              : "rgba(40,40,60,0.6)",
            boxShadow: hasContent && !isLoading ? "0 0 14px rgba(203,166,247,0.4)" : "none",
          }}
          aria-label={isLoading ? "Running…" : "Submit"}
        >
          {isLoading
            ? <span className="w-3 h-3 border border-white/40 border-t-white/90 rounded-full animate-spin" />
            : <ArrowUp size={14} color="#fff" />
          }
        </motion.button>
      </motion.div>

      {/* Hint text */}
      <AnimatePresence>
        {focused && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-center text-[10px] font-sans mt-2"
            style={{ color: "#35354d" }}
          >
            Enter to submit · Shift+Enter for newline · Drop files to attach
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
