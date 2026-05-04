"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Search, Upload, Eye, ThumbsUp, MessageCircle, Film, RefreshCw } from "lucide-react";
import { useProjectStore } from "@/stores/project";
import { StudioCard } from "@/components/studio/StudioCard";
import { useState, useEffect, useCallback } from "react";
import { getYoutubeVideos } from "@/lib/api";

interface YouTubeVideo {
  id: string;
  title: string;
  thumbnail: string;
  url: string;
  views: string;
  likes: string;
  comments: string;
  published: string;
}

export function StageSelectMovie() {
  const { createProject } = useProjectStore();
  const [selected, setSelected] = useState<string | null>(null);
  const [videos, setVideos] = useState<YouTubeVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const signal = AbortSignal.timeout(8000);
      const data = await getYoutubeVideos(signal);
      const mapped: YouTubeVideo[] = (data.videos || []).map((v: unknown) => {
        const anyV = v as Record<string, unknown>;
        return {
          id: String(anyV.id ?? crypto.randomUUID()),
          title: String(anyV.title ?? "Untitled"),
          thumbnail: String(anyV.thumbnail ?? ""),
          url: String(anyV.url ?? ""),
          views: String(anyV.views ?? "—"),
          likes: String(anyV.likes ?? "—"),
          comments: String(anyV.comments ?? "—"),
          published: String(anyV.published ?? ""),
        };
      });
      setVideos(mapped);
    } catch {
      setVideos(FALLBACK_VIDEOS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => fetchVideos(), 0);
    return () => clearTimeout(timer);
  }, [fetchVideos]);

  const formatNumber = (n: string): string => {
    if (n === "—" || !n) return "—";
    if (n.includes("K") || n.includes("M")) return n;
    const num = parseInt(n.replace(/[^0-9]/g, ""));
    if (isNaN(num)) return n;
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return n;
  };

  return (
    <motion.div className="h-full flex flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      {/* Header cinematográfico */}
      <div className="relative px-8 py-8"
        style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}
      >
        <div className="flex items-center gap-4">
          <motion.div
            className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
            style={{
              background: "linear-gradient(135deg, rgba(232,162,79,0.15), rgba(96,165,250,0.1))",
              border: "1px solid rgba(232,162,79,0.2)",
              boxShadow: "0 0 24px rgba(232,162,79,0.1)",
            }}
            whileHover={{ scale: 1.05, rotate: 5 }}
          >
            <Film size={22} className="text-accent-purple-soft" />
          </motion.div>
          <div>
            <h1 className="text-2xl font-bold text-text-primary tracking-tight">Tus Videos de YouTube</h1>
            <p className="text-sm text-text-muted mt-0.5">Selecciona un video para crear un recap con IA</p>
          </div>
        </div>
      </div>

      {/* Controles */}
      <div className="flex items-center gap-3 px-8 py-4">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            className="w-full h-9 pl-9 pr-4 rounded-lg text-sm text-text-primary placeholder:text-text-muted focus:outline-none transition-all"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(30,30,50,0.5)",
            }}
            placeholder="Buscar videos..."
          />
        </div>
        <motion.button
          className="flex items-center gap-2 h-9 px-4 rounded-lg text-sm text-text-secondary transition-all"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(30,30,50,0.5)",
          }}
          whileHover={{ borderColor: "rgba(96,165,250,0.25)", background: "rgba(96,165,250,0.04)" }}
          whileTap={{ scale: 0.98 }}
        >
          <Upload size={14} />Importar desde URL
        </motion.button>
        <motion.button
          className="flex items-center gap-2 h-9 px-3 rounded-lg text-sm text-text-secondary transition-all"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(30,30,50,0.5)",
          }}
          onClick={fetchVideos}
          whileHover={{ borderColor: "rgba(232,162,79,0.25)", background: "rgba(232,162,79,0.04)" }}
          whileTap={{ scale: 0.98 }}
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </motion.button>
      </div>

      {/* Loading */}
      <AnimatePresence>
        {loading && (
          <motion.div
            className="flex-1 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="text-center space-y-4">
              <motion.div
                className="w-12 h-12 rounded-2xl mx-auto"
                style={{
                  border: "2px solid rgba(232,162,79,0.2)",
                  borderTopColor: "#E8A24F",
                  boxShadow: "0 0 20px rgba(232,162,79,0.1)",
                }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
              />
              <p className="text-sm text-text-tertiary">Conectando con YouTube Studio...</p>
              <p className="text-xs text-text-muted">Extrayendo tus videos y métricas</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error */}
      <AnimatePresence>
        {error && !loading && (
          <motion.div
            className="flex-1 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="text-center">
              <p className="text-sm text-error mb-2">Error al cargar videos</p>
              <p className="text-xs text-text-muted mb-4">{error}</p>
              <motion.button
                onClick={fetchVideos}
                className="px-4 py-2 rounded-lg text-accent-purple-soft text-sm"
                style={{
                  background: "rgba(232,162,79,0.08)",
                  border: "1px solid rgba(232,162,79,0.15)",
                }}
                whileHover={{ background: "rgba(232,162,79,0.15)" }}
              >
                Reintentar
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Grid */}
      <AnimatePresence>
        {!loading && (
          <motion.div
            className="flex-1 overflow-y-auto px-8 pb-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-4">
              {videos.map((video, i) => (
                <motion.div
                  key={video.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.06 }}
                >
                  <StudioCard
                    aspectRatio="video"
                    glow="purple"
                    selected={selected === video.id}
                    onClick={() => {
                      setSelected(video.id);
                      createProject(video.title, video.title, video.url ?? "");
                    }}
                  >
                    <div className="relative w-full h-full"
                      style={{ background: "linear-gradient(135deg, #0E0E18, #08080F)" }}
                    >
                      {video.thumbnail ? (
                        <img
                          src={video.thumbnail}
                          alt={video.title}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center"
                          style={{
                            background: "linear-gradient(135deg, rgba(232,162,79,0.15), rgba(96,165,250,0.1), rgba(14,14,24,0.5))",
                          }}
                        >
                          <Film size={24} className="text-text-muted" />
                        </div>
                      )}
                      <div
                        className="absolute inset-x-0 bottom-0 p-3"
                        style={{
                          background: "linear-gradient(to top, rgba(2,2,5,0.95) 0%, rgba(2,2,5,0.6) 60%, transparent 100%)",
                        }}
                      >
                        <h3 className="text-xs font-semibold text-white leading-tight line-clamp-2 mb-2">
                          {video.title}
                        </h3>
                        <div className="flex items-center gap-3 text-[10px] text-white/60">
                          <span className="flex items-center gap-1">
                            <Eye size={10} />{formatNumber(video.views)}
                          </span>
                          <span className="flex items-center gap-1">
                            <ThumbsUp size={10} />{formatNumber(video.likes)}
                          </span>
                          <span className="flex items-center gap-1">
                            <MessageCircle size={10} />{formatNumber(video.comments)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {selected === video.id && (
                      <motion.div
                        className="absolute top-3 right-3 w-6 h-6 rounded-full flex items-center justify-center"
                        style={{
                          background: "linear-gradient(135deg, #E8A24F, #C47A28)",
                          boxShadow: "0 0 12px rgba(232,162,79,0.4)",
                        }}
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", stiffness: 500, damping: 20 }}
                      >
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                          <path d="M2.5 6L5 8.5L9.5 3.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </motion.div>
                    )}
                  </StudioCard>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

const FALLBACK_VIDEOS: YouTubeVideo[] = [
  { id: "fb-1", title: "El Misterio del Universo: Agujeros Negros Explicados", thumbnail: "", url: "", views: "12.4K", likes: "843", comments: "126", published: "" },
  { id: "fb-2", title: "Viaje al Centro de la Galaxia: Lo que la NASA no te cuenta", thumbnail: "", url: "", views: "8.7K", likes: "612", comments: "89", published: "" },
  { id: "fb-3", title: "¿Qué pasaría si el Sol desapareciera mañana?", thumbnail: "", url: "", views: "45.2K", likes: "2.1K", comments: "340", published: "" },
  { id: "fb-4", title: "Documental: Los Secretos de Marte revelados", thumbnail: "", url: "", views: "3.2K", likes: "278", comments: "45", published: "" },
  { id: "fb-5", title: "Teoría del Multiverso: ¿Existen copias tuyas en otros universos?", thumbnail: "", url: "", views: "28.9K", likes: "1.4K", comments: "210", published: "" },
  { id: "fb-6", title: "Los 5 Planetas más Extraños del Universo Conocido", thumbnail: "", url: "", views: "19.3K", likes: "956", comments: "132", published: "" },
];
