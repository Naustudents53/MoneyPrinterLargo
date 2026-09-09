import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { hfApi } from "../lib/higgsfield";

const PHASE_LABELS: Record<string, string> = {
  init: "Initializing", topic_analysis: "Analyzing Topic", research: "Researching",
  concept: "Creative Concept", narrative: "Narrative", script: "Writing Script",
  segmentation: "Segmenting", visual_bible: "Visual Bible", character_bible: "Characters",
  environment_bible: "Environments", storyboard: "Storyboard", shot_planning: "Shot Planning",
  prompt_engineering: "Prompts", reference_prep: "References", generation: "Generating",
  video_qc: "QC", regeneration: "Regenerating", audio: "Audio", assembly: "Assembling",
  final_qc: "Final QC", metadata: "Metadata", thumbnail: "Thumbnail", publishing: "Publishing",
  completed: "Completed", failed: "Failed", paused: "Paused", cancelled: "Cancelled",
};

const TABS = ["overview", "script", "storyboard", "shots", "timeline", "cost"] as const;
type Tab = typeof TABS[number];

export function HiggsfieldProject() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [project, setProject] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [tabData, setTabData] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!id) return;
    hfApi.getProject(id).then(setProject).catch(() => nav("/higgsfield"));
  }, [id]);

  useEffect(() => {
    if (!id || tab === "overview") { setTabData(null); return; }
    const fetchers: Record<string, () => Promise<any>> = {
      script: () => hfApi.getScript(id),
      storyboard: () => hfApi.getStoryboard(id),
      shots: () => hfApi.getShots(id),
      timeline: () => hfApi.getTimeline(id),
      cost: () => hfApi.getCost(id),
    };
    fetchers[tab]?.().then(setTabData);
  }, [id, tab]);

  const startProduction = () => {
    if (!id) return;
    setRunning(true);
    setLogs([]);
    const es = new EventSource(hfApi.runProductionUrl(id));
    esRef.current = es;
    es.addEventListener("start", (e) => setLogs((l) => [...l, `Started: ${e.data}`]));
    es.addEventListener("phase_started", (e) => {
      const d = JSON.parse(e.data);
      setLogs((l) => [...l, `[phase] ${PHASE_LABELS[d.phase] || d.phase} (${d.progress?.toFixed(0)}%)`]);
    });
    es.addEventListener("phase_completed", (e) => {
      const d = JSON.parse(e.data);
      setLogs((l) => [...l, `[done] ${PHASE_LABELS[d.phase] || d.phase}`]);
    });
    es.addEventListener("shot_started", (e) => {
      const d = JSON.parse(e.data);
      setLogs((l) => [...l, `[shot] Shot ${d.sequence}`]);
    });
    es.addEventListener("shot_completed", (e) => setLogs((l) => [...l, "  Shot completed"]));
    es.addEventListener("shot_failed", (e) => {
      const d = JSON.parse(e.data);
      setLogs((l) => [...l, `  Shot failed: ${d.error}`]);
    });
    es.addEventListener("phase_failed", (e) => {
      const d = JSON.parse(e.data);
      setLogs((l) => [...l, `[fail] ${d.phase}: ${d.error}`]);
    });
    es.addEventListener("error", () => { setLogs((l) => [...l, "Connection error"]); });
    es.addEventListener("done", (e) => {
      const d = JSON.parse(e.data);
      setLogs((l) => [...l, d.error ? `Error: ${d.error}` : "Production complete"]);
      setRunning(false);
      es.close();
      if (id) hfApi.getProject(id).then(setProject);
    });
  };

  if (!project) return <div className="text-zinc-500">Loading...</div>;

  const isActive = !["completed", "failed", "cancelled"].includes(project.phase);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={() => nav("/higgsfield")} className="text-xs text-zinc-500 hover:text-zinc-300 mb-1">
            &larr; Back to Studio
          </button>
          <h1 className="text-xl font-semibold">{project.config?.title || project.config?.topic}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm">
            <span className={project.phase === "completed" ? "text-emerald-400" : project.phase === "failed" ? "text-red-400" : "text-blue-400"}>
              {PHASE_LABELS[project.phase] || project.phase}
            </span>
            {project.progress > 0 && project.progress < 100 && (
              <div className="w-40 h-1.5 bg-zinc-800 rounded-full">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${project.progress}%` }} />
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {isActive && !running && (
            <button onClick={startProduction}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
              {project.phase === "init" ? "Start Production" : "Resume"}
            </button>
          )}
          {running && (
            <button onClick={() => { esRef.current?.close(); hfApi.cancelProduction(id!); setRunning(false); }}
              className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700">
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-zinc-800 pb-px">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm rounded-t-lg transition ${tab === t ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-300"}`}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-[300px]">
        {tab === "overview" && <OverviewTab project={project} logs={logs} running={running} />}
        {tab === "script" && <ScriptTab data={tabData} />}
        {tab === "storyboard" && <StoryboardTab data={tabData} />}
        {tab === "shots" && <ShotsTab data={tabData} projectId={id!} onRefresh={() => hfApi.getShots(id!).then(setTabData)} />}
        {tab === "timeline" && <TimelineTab data={tabData} />}
        {tab === "cost" && <CostTab data={tabData} />}
      </div>
    </div>
  );
}

function OverviewTab({ project, logs, running }: { project: any; logs: string[]; running: boolean }) {
  const config = project.config || {};
  return (
    <div className="grid grid-cols-2 gap-6">
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">Production Info</h3>
        <div className="grid grid-cols-2 gap-2 text-sm">
          {[["Genre", config.genre], ["Duration", `${config.target_duration_min} min`],
            ["Quality", config.quality], ["Aspect", config.aspect_ratio],
            ["Language", config.language], ["Provider", config.provider],
            ["Mode", config.director_mode], ["Research", config.research_mode],
            ["Budget", config.budget_limit ? `$${config.budget_limit}` : "None"],
            ["Dry Run", config.dry_run ? "Yes" : "No"],
          ].map(([k, v]) => (
            <div key={k as string}>
              <span className="text-zinc-500">{k}: </span>
              <span className="text-zinc-300">{v}</span>
            </div>
          ))}
        </div>
        {project.concept && (
          <div>
            <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-2">Concept</h3>
            <p className="text-sm text-zinc-300 whitespace-pre-wrap">{project.concept.slice(0, 500)}</p>
          </div>
        )}
      </div>
      <div>
        <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-2">Production Log</h3>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 h-80 overflow-y-auto font-mono text-xs space-y-0.5">
          {logs.length === 0 && !running && <span className="text-zinc-600">No activity yet</span>}
          {logs.map((l, i) => <div key={i} className="text-zinc-400">{l}</div>)}
          {running && <div className="text-blue-400 animate-pulse">Processing...</div>}
        </div>
      </div>
    </div>
  );
}

function ScriptTab({ data }: { data: any }) {
  if (!data) return <div className="text-zinc-500 text-sm">Loading script...</div>;
  return (
    <div className="space-y-6">
      {data.concept && (
        <div>
          <h3 className="text-sm font-medium text-zinc-400 mb-2">Concept</h3>
          <p className="text-sm text-zinc-300 whitespace-pre-wrap bg-zinc-900 rounded-lg p-4 border border-zinc-800">{data.concept}</p>
        </div>
      )}
      {data.chapters?.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-zinc-400 mb-2">Chapters</h3>
          <div className="space-y-1">
            {data.chapters.map((ch: any, i: number) => (
              <div key={i} className="flex gap-3 text-sm border-b border-zinc-800/50 py-2">
                <span className="text-zinc-500 w-16">{formatTime(ch.start_sec)}</span>
                <span className="text-zinc-300">{ch.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {data.narration_blocks?.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-zinc-400 mb-2">Narration ({data.narration_blocks.length} blocks)</h3>
          <div className="space-y-3">
            {data.narration_blocks.map((b: any, i: number) => (
              <div key={i} className="bg-zinc-900 rounded-lg p-3 border border-zinc-800 text-sm">
                <div className="flex gap-2 text-xs text-zinc-500 mb-1">
                  <span className="font-medium text-zinc-400">{b.narrative_element || "block"}</span>
                  <span>{formatTime(b.start_sec)} - {formatTime(b.end_sec)}</span>
                  {b.emotion && <span className="italic">{b.emotion}</span>}
                </div>
                <p className="text-zinc-300">{b.text}</p>
                {b.visual_intent && <p className="text-xs text-blue-400/70 mt-1">Visual: {b.visual_intent}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StoryboardTab({ data }: { data: any }) {
  if (!data) return <div className="text-zinc-500 text-sm">Loading storyboard...</div>;
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-zinc-400">Scenes ({data.scenes?.length || 0})</h3>
      <div className="flex gap-3 overflow-x-auto pb-4">
        {(data.scenes || []).map((s: any, i: number) => (
          <div key={i} className="min-w-[200px] bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm flex-shrink-0">
            <div className="flex justify-between items-center mb-2">
              <span className="font-medium text-zinc-300">Scene {s.sequence + 1}</span>
              <span className="text-xs text-zinc-500">{formatTime(s.timecode_start)}</span>
            </div>
            <p className="text-xs text-zinc-400 line-clamp-3">{s.visual_goal}</p>
            <div className="flex gap-2 mt-2 text-xs text-zinc-600">
              <span>{s.duration_sec?.toFixed(1)}s</span>
              <span>{(s.shot_ids || []).length} shots</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ShotsTab({ data, projectId, onRefresh }: { data: any; projectId: string; onRefresh: () => void }) {
  if (!data) return <div className="text-zinc-500 text-sm">Loading shots...</div>;
  const shots = data.shots || [];

  const doAction = async (shotId: string, action: string) => {
    await hfApi.shotAction(projectId, shotId, action);
    onRefresh();
  };

  const statusColor: Record<string, string> = {
    approved: "text-emerald-400", rejected: "text-red-400", failed: "text-red-500",
    generating: "text-blue-400", planned: "text-zinc-500", qc_pending: "text-amber-400",
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-medium text-zinc-400">Shots ({shots.length})</h3>
        <div className="flex gap-3 text-xs text-zinc-500">
          <span className="text-emerald-400">{shots.filter((s: any) => s.status === "approved").length} approved</span>
          <span className="text-red-400">{shots.filter((s: any) => s.status === "failed" || s.status === "rejected").length} failed</span>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {shots.map((s: any) => (
          <div key={s.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm">
            <div className="flex justify-between items-start mb-2">
              <div>
                <span className="font-medium text-zinc-300">#{s.sequence}</span>
                <span className="text-xs text-zinc-600 ml-2">{s.shot_type?.replace("_", " ")}</span>
              </div>
              <span className={`text-xs ${statusColor[s.status] || "text-zinc-500"}`}>{s.status}</span>
            </div>
            {s.subject && <p className="text-xs text-zinc-400 mb-1">{s.subject}</p>}
            <div className="flex gap-2 text-xs text-zinc-600 mb-2">
              <span>{s.duration_sec?.toFixed(1)}s</span>
              <span>{s.model_id}</span>
              {s.prompt_quality_score > 0 && <span>QC: {s.prompt_quality_score.toFixed(0)}</span>}
            </div>
            {(s.optimized_prompt || s.prompt) && (
              <details className="mb-2">
                <summary className="text-xs text-blue-400 cursor-pointer">Prompt</summary>
                <p className="text-xs text-zinc-400 mt-1 whitespace-pre-wrap">{s.optimized_prompt || s.prompt}</p>
              </details>
            )}
            <div className="flex gap-1.5">
              {s.status !== "approved" && (
                <button onClick={() => doAction(s.id, "approve")} className="text-xs px-2 py-0.5 bg-emerald-900/50 text-emerald-400 rounded hover:bg-emerald-900">Approve</button>
              )}
              {s.status !== "rejected" && (
                <button onClick={() => doAction(s.id, "reject")} className="text-xs px-2 py-0.5 bg-red-900/50 text-red-400 rounded hover:bg-red-900">Reject</button>
              )}
              <button onClick={() => doAction(s.id, "regenerate")} className="text-xs px-2 py-0.5 bg-zinc-800 text-zinc-400 rounded hover:bg-zinc-700">Regen</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineTab({ data }: { data: any }) {
  if (!data) return <div className="text-zinc-500 text-sm">Loading timeline...</div>;
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-zinc-400">Timeline</h3>
      {(data.timeline || []).map((entry: any, i: number) => (
        <div key={i} className="flex items-center gap-3 text-sm border-l-2 border-zinc-700 pl-3 py-1">
          <span className="text-zinc-500 font-mono w-20">{formatTime(entry.start)}</span>
          <div className="flex-1">
            <span className="text-zinc-300">{entry.visual_goal || `Scene`}</span>
            <span className="text-xs text-zinc-600 ml-2">{entry.duration?.toFixed(1)}s | {entry.shot_count} shots</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function CostTab({ data }: { data: any }) {
  if (!data) return <div className="text-zinc-500 text-sm">Loading cost info...</div>;
  const s = data.summary || {};
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-zinc-400">Cost Summary</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          ["Estimated", s.total_estimated != null ? `$${s.total_estimated.toFixed(2)}` : "N/A"],
          ["Actual", s.total_actual != null ? `$${s.total_actual.toFixed(2)}` : "N/A"],
          ["Budget", s.budget_limit != null ? `$${s.budget_limit}` : "None"],
          ["Shots", `${s.completed_shots || 0}/${s.total_shots || 0}`],
        ].map(([k, v]) => (
          <div key={k as string} className="bg-zinc-900 rounded-lg p-3 border border-zinc-800">
            <div className="text-xs text-zinc-500">{k}</div>
            <div className="text-lg font-medium mt-1">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatTime(sec: number | undefined): string {
  if (sec == null) return "--";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
