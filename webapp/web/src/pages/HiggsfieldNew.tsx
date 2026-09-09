import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { hfApi, NewProductionInput } from "../lib/higgsfield";

const GENRES = [
  "documentary", "true_crime", "science", "history", "mystery", "horror",
  "space", "technology", "nature", "travel", "sports", "business",
  "fiction", "explainer", "cinematic_essay", "war", "architecture",
];
const QUALITIES = ["budget", "balanced", "quality", "cinema"];
const ASPECTS = ["16:9", "21:9", "9:16", "1:1"];
const DURATIONS = [3, 5, 7, 10, 15, 20, 25, 30, 45, 60];
const LANGUAGES = [
  { code: "es", label: "Spanish" }, { code: "en", label: "English" },
  { code: "pt", label: "Portuguese" }, { code: "fr", label: "French" },
  { code: "de", label: "German" }, { code: "it", label: "Italian" },
];

export function HiggsfieldNew() {
  const nav = useNavigate();
  const [form, setForm] = useState<NewProductionInput>({
    topic: "", title: "", target_duration_min: 15, aspect_ratio: "16:9",
    resolution: "1080p", language: "es", genre: "documentary",
    quality: "quality", research_mode: "light", director_mode: "auto",
    production_mode: "full", budget_limit: 50, dry_run: false,
  });
  const [submitting, setSubmitting] = useState(false);

  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.topic.trim()) return;
    setSubmitting(true);
    try {
      const { id } = await hfApi.createProject(form);
      nav(`/higgsfield/${id}`);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">New Production</h1>
        <p className="text-sm text-zinc-500 mt-1">Configure your cinematic video production</p>
      </div>

      <div className="space-y-5">
        {/* Topic */}
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1.5">Topic *</label>
          <textarea
            value={form.topic}
            onChange={(e) => set("topic", e.target.value)}
            placeholder="e.g., The disappearance of flight MH370..."
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm resize-none h-20 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>

        {/* Title */}
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1.5">Title</label>
          <input
            value={form.title || ""}
            onChange={(e) => set("title", e.target.value)}
            placeholder="Auto-generated if empty"
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
          />
        </div>

        {/* Grid */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Duration (min)</label>
            <select value={form.target_duration_min} onChange={(e) => set("target_duration_min", Number(e.target.value))}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              {DURATIONS.map((d) => <option key={d} value={d}>{d} min</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Aspect Ratio</label>
            <select value={form.aspect_ratio} onChange={(e) => set("aspect_ratio", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              {ASPECTS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Language</label>
            <select value={form.language} onChange={(e) => set("language", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Genre</label>
            <select value={form.genre} onChange={(e) => set("genre", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              {GENRES.map((g) => <option key={g} value={g}>{g.replace("_", " ")}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Quality</label>
            <select value={form.quality} onChange={(e) => set("quality", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              {QUALITIES.map((q) => <option key={q} value={q}>{q.charAt(0).toUpperCase() + q.slice(1)}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Research</label>
            <select value={form.research_mode} onChange={(e) => set("research_mode", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              <option value="none">None</option>
              <option value="light">Light</option>
              <option value="deep">Deep</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Mode</label>
            <select value={form.director_mode} onChange={(e) => set("director_mode", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              <option value="auto">Auto Director</option>
              <option value="director">Director Mode</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Production</label>
            <select value={form.production_mode} onChange={(e) => set("production_mode", e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm">
              <option value="plan">Plan Only</option>
              <option value="plan_prompts">Plan + Prompts</option>
              <option value="full">Full Production</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Budget ($)</label>
            <input type="number" value={form.budget_limit ?? ""} onChange={(e) => set("budget_limit", e.target.value ? Number(e.target.value) : null)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm" placeholder="No limit" />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
              <input type="checkbox" checked={form.dry_run} onChange={(e) => set("dry_run", e.target.checked)}
                className="rounded border-zinc-600" />
              Dry Run
            </label>
          </div>
        </div>
      </div>

      <div className="flex gap-3 pt-2">
        <button onClick={() => nav("/higgsfield")}
          className="px-4 py-2 border border-zinc-700 rounded-lg text-sm hover:bg-zinc-800 transition">
          Cancel
        </button>
        <button onClick={submit} disabled={submitting || !form.topic.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition">
          {submitting ? "Creating..." : "Create Production"}
        </button>
      </div>
    </div>
  );
}
