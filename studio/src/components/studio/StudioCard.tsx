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

const aspectClasses = {
  poster: "aspect-[3/4]",
  video: "aspect-video",
  square: "aspect-square",
};

export function StudioCard({
  children,
  className,
  glow = "none",
  onClick,
  selected = false,
  aspectRatio = "video",
}: StudioCardProps) {
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
      className={cn(
        "relative rounded-xl border cursor-pointer overflow-hidden group",
        aspectClasses[aspectRatio],
        className
      )}
      style={
        selected
          ? {
              background: "linear-gradient(135deg, rgba(232,162,79,0.1), rgba(96,165,250,0.05))",
              border: "1px solid rgba(232,162,79,0.3)",
              boxShadow: "0 0 30px rgba(232,162,79,0.15), inset 0 1px 0 rgba(255,255,255,0.03)",
            }
          : {
              background: "linear-gradient(135deg, rgba(21,21,32,0.8), rgba(14,14,24,0.9))",
              border: "1px solid rgba(30,30,50,0.4)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)",
            }
      }
      whileHover={{
        y: -4,
        borderColor: glow === "purple"
          ? "rgba(232,162,79,0.25)"
          : glow === "blue"
          ? "rgba(96,165,250,0.25)"
          : "rgba(30,30,50,0.6)",
        boxShadow: glow === "purple"
          ? "0 0 30px rgba(232,162,79,0.1), inset 0 1px 0 rgba(255,255,255,0.03)"
          : glow === "blue"
          ? "0 0 30px rgba(96,165,250,0.1), inset 0 1px 0 rgba(255,255,255,0.03)"
          : "0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03)",
      }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      layout
    >
      {(glow === "purple" || glow === "blue") && (
        <div
          className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 pointer-events-none z-10 transition-opacity duration-300"
          style={{
            background:
              glow === "purple"
                ? "radial-gradient(600px circle at var(--mx, 50%) var(--my, 50%), rgba(232,162,79,0.1), transparent 60%)"
                : "radial-gradient(600px circle at var(--mx, 50%) var(--my, 50%), rgba(96,165,250,0.1), transparent 60%)",
          }}
        />
      )}
      {children}
    </motion.div>
  );
}
