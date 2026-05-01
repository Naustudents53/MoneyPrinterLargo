"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useRef } from "react";

interface StudioCardProps {
  children: React.ReactNode;
  className?: string;
  glow?: "purple" | "blue" | "none";
  onClick?: () => void;
  selected?: boolean;
  aspectRatio?: "poster" | "video" | "square";
}

const aspectClasses = { poster: "aspect-[3/4]", video: "aspect-video", square: "aspect-square" };

export function StudioCard({ children, className, glow = "none", onClick, selected = false, aspectRatio = "video" }: StudioCardProps) {
  const ref = useRef<HTMLDivElement>(null);

  const handleMouseMove = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const { left, top, width, height } = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${((e.clientX - left) / width) * 100}%`);
    el.style.setProperty("--my", `${((e.clientY - top) / height) * 100}%`);
  };

  return (
    <motion.div
      ref={ref}
      className={cn("relative rounded-xl border cursor-pointer overflow-hidden group bg-surface-raised border-border-subtle",
        selected && "border-accent-purple shadow-glow-purple",
        glow === "purple" && "hover:border-accent-purple hover:shadow-glow-purple",
        glow === "blue" && "hover:border-accent-blue hover:shadow-glow-blue",
        aspectClasses[aspectRatio], className)}
      whileHover={{ y: -4 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      layout
    >
      {(glow === "purple" || glow === "blue") && (
        <div className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 pointer-events-none z-10 transition-opacity duration-300"
          style={{ background: glow === "purple" ? "radial-gradient(600px circle at var(--mx, 50%) var(--my, 50%), rgba(124,58,237,0.08), transparent 60%)" : "radial-gradient(600px circle at var(--mx, 50%) var(--my, 50%), rgba(59,130,246,0.08), transparent 60%)" }}
        />
      )}
      {children}
    </motion.div>
  );
}
