"use client";

import { motion } from "framer-motion";
import { Search, Upload, Star, Clock, Film } from "lucide-react";
import { useProjectStore } from "@/stores/project";
import { StudioCard } from "@/components/studio/StudioCard";
import { useState } from "react";

const SAMPLE_MOVIES = [
  { title: "Metropolis", year: "1927", rating: 8.3, duration: "148 min", genre: "Sci-Fi", gradient: "from-indigo-900 via-purple-800 to-black", initials: "ME" },
  { title: "Nosferatu", year: "1922", rating: 7.9, duration: "94 min", genre: "Horror", gradient: "from-red-900 via-gray-800 to-black", initials: "NO" },
  { title: "The Lost World", year: "1925", rating: 7.0, duration: "106 min", genre: "Adventure", gradient: "from-emerald-900 via-teal-800 to-black", initials: "LW" },
  { title: "The Cabinet of Dr. Caligari", year: "1920", rating: 8.0, duration: "76 min", genre: "Horror", gradient: "from-amber-900 via-yellow-800 to-black", initials: "TC" },
  { title: "The General", year: "1926", rating: 8.1, duration: "79 min", genre: "Comedy", gradient: "from-cyan-900 via-blue-800 to-black", initials: "TG" },
  { title: "Battleship Potemkin", year: "1925", rating: 7.9, duration: "75 min", genre: "Drama", gradient: "from-rose-900 via-red-800 to-black", initials: "BP" },
  { title: "The Phantom of the Opera", year: "1925", rating: 7.6, duration: "93 min", genre: "Horror", gradient: "from-violet-900 via-purple-800 to-black", initials: "TP" },
  { title: "Steamboat Willie", year: "1928", rating: 7.4, duration: "8 min", genre: "Animation", gradient: "from-sky-900 via-blue-800 to-black", initials: "SW" },
];

export function StageSelectMovie() {
  const { createProject } = useProjectStore();
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <motion.div className="h-full flex flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="relative px-8 py-8 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <motion.div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent-purple to-accent-blue flex items-center justify-center" whileHover={{ scale: 1.05, rotate: 5 }}>
            <Film size={20} className="text-white" />
          </motion.div>
          <div><h1 className="text-2xl font-bold text-text-primary tracking-tight">Select a Movie</h1><p className="text-sm text-text-tertiary">Choose from public domain classics to create your recap</p></div>
        </div>
      </div>

      <div className="flex items-center gap-3 px-8 py-4">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input className="w-full h-9 pl-9 pr-4 rounded-lg bg-surface-raised border border-border-subtle text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent-purple/50 transition-colors" placeholder="Search movies..." />
        </div>
        <motion.button className="flex items-center gap-2 h-9 px-4 rounded-lg border border-border-subtle bg-surface-raised text-sm text-text-secondary hover:border-border-default hover:text-text-primary transition-colors" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}><Upload size={14} />Import from URL</motion.button>
      </div>

      <div className="flex-1 overflow-y-auto px-8 pb-8">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-4">
          {SAMPLE_MOVIES.map((movie, i) => (
            <motion.div key={movie.title} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.06 }}>
              <StudioCard aspectRatio="poster" glow="purple" selected={selected === movie.title}
                onClick={() => { setSelected(movie.title); createProject("New Production", movie.title); }}>
                <div className={`absolute inset-0 bg-gradient-to-br ${movie.gradient} flex items-center justify-center`}>
                  <span className="text-4xl font-black text-white/20">{movie.initials}</span>
                </div>
                <div className="absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-black/90 via-black/50 to-transparent">
                  <div className="flex items-center gap-1 text-xs text-amber-400 mb-0.5"><Star size={10} className="fill-amber-400" />{movie.rating}</div>
                  <h3 className="text-sm font-semibold text-white leading-tight">{movie.title}</h3>
                  <div className="flex items-center gap-2 mt-0.5 text-[10px] text-white/60"><span>{movie.year}</span><span>·</span><span className="flex items-center gap-1"><Clock size={9} />{movie.duration}</span><span>·</span><span>{movie.genre}</span></div>
                </div>
                {selected === movie.title && (
                  <motion.div className="absolute top-3 right-3 w-6 h-6 rounded-full bg-accent-purple flex items-center justify-center shadow-glow-purple" initial={{ scale: 0 }} animate={{ scale: 1 }}>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6L5 8.5L9.5 3.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  </motion.div>
                )}
              </StudioCard>
            </motion.div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
