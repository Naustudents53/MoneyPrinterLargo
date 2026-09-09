import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { hfApi, HFProject } from "../lib/higgsfield";

const PHASE_LABELS: Record<string, string> = {
  init: "Initializing", topic_analysis: "Analyzing Topic", research: "Researching",
  concept: "Creative Concept", narrative: "Narrative Architecture", script: "Writing Script",
  segmentation: "Segmenting", visual_bible: "Visual Bible", character_bible: "Character Bible",
  environment_bible: "Environment Bible", storyboard: "Storyboard", shot_planning: "Planning Shots",
  prompt_engineering: "Engineering Prompts", reference_prep: "Preparing References",
  generation: "Generating Video", video_qc: "Quality Control", regeneration: "Regenerating",
  audio: "Audio Production", assembly: "Assembling", final_qc: "Final QC",
  metadata: "Metadata", thumbnail: "Thumbnail", publishing: "Publishing",
  completed: "Completed", failed: "Failed", paused: "Paused", cancelled: "Cancelled",
};

function phaseColor(phase: string) {
  if (phase === "completed") return "text-emerald-400";
  if (phase === "failed") return "text-red-400";
  if (phase === "paused") return "text-amber-400";
  if (phase === "cancelled") return "text-zinc-500";
  return "text-blue-400";
}

export function HiggsfieldStudio() {
  const [projects, setProjects] = useState<HFProject[]>([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    hfApi.listProjects().then(setProjects).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Higgsfield Studio</h1>
          <p className="text-sm text-zinc-500 mt-1">Cinematic long-form video production</p>
        </div>
        <button
          onClick={() => nav("/higgsfield/new")}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition text-sm font-medium"
        >
          New Production
        </button>
      </div>

      {loading ? (
        <div className="text-zinc-500 text-sm">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="border border-dashed border-zinc-700 rounded-xl p-12 text-center">
          <p className="text-zinc-400 text-lg">No productions yet</p>
          <p className="text-zinc-600 text-sm mt-2">
            Create your first cinematic production to get started.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => nav(`/higgsfield/${p.id}`)}
              className="w-full text-left border border-zinc-800 rounded-lg p-4 hover:border-zinc-600 transition bg-zinc-900/50"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium">{p.title || p.topic}</h3>
                  <p className="text-xs text-zinc-500 mt-1">{p.topic}</p>
                </div>
                <div className="text-right">
                  <span className={`text-sm font-medium ${phaseColor(p.phase)}`}>
                    {PHASE_LABELS[p.phase] || p.phase}
                  </span>
                  {p.progress > 0 && p.progress < 100 && (
                    <div className="w-32 h-1.5 bg-zinc-800 rounded-full mt-2">
                      <div
                        className="h-full bg-blue-500 rounded-full transition-all"
                        style={{ width: `${p.progress}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
              <div className="flex gap-4 mt-2 text-xs text-zinc-600">
                <span>{new Date(p.created_at * 1000).toLocaleDateString()}</span>
                <span>v{p.version}</span>
                {p.error && <span className="text-red-500 truncate max-w-xs">{p.error}</span>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
