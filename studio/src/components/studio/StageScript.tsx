"use client";

import { motion } from "framer-motion";
import { Clapperboard, Clock, GripVertical, Star } from "lucide-react";
import { useProjectStore } from "@/stores/project";
import { ScrollArea } from "@/components/ui/scroll-area";

const SAMPLE_SCENES = [
  { id: "1", title: "Opening — The Machine City", timestamp: "00:00 — 02:15", description: "Establishing shots of Metropolis. Workers march in synchronized patterns.", importance: 0.95 },
  { id: "2", title: "The Eternal Gardens", timestamp: "02:16 — 04:30", description: "Freder frolics with the elite in the pleasure gardens above the city.", importance: 0.85 },
  { id: "3", title: "Maria Arrives", timestamp: "04:31 — 06:45", description: "Maria brings the workers' children to see the privileged world above.", importance: 0.92 },
  { id: "4", title: "The Heart Machine", timestamp: "06:46 — 09:20", description: "An explosion at the central power plant. Workers struggle at the machine.", importance: 0.88 },
  { id: "5", title: "Freder's Vision", timestamp: "09:21 — 11:40", description: "Freder hallucinates the machine as Moloch consuming workers.", importance: 0.90 },
  { id: "6", title: "Rotwang's Laboratory", timestamp: "11:41 — 14:00", description: "The inventor reveals his robot. Plans to resurrect his lost love Hel.", importance: 0.87 },
  { id: "7", title: "The Transformation", timestamp: "14:01 — 17:30", description: "Robot Maria comes to life. Light rings circle the machine. Cinematic peak.", importance: 0.97 },
  { id: "8", title: "False Maria Corrupts", timestamp: "17:31 — 20:00", description: "Robot Maria dances at Yoshiwara. Men fight over her. City descends into chaos.", importance: 0.89 },
];

const SCRIPT = `METROPOLIS \u2014 A RETROSPECTIVE

CHAPTER 1: THE MACHINE CITY

In the year 2026, the gleaming towers of Metropolis pierce the heavens. Below, in the catacombs, thousands of workers move in hypnotic synchronization, feeding the great machines that power the city above.

Freder, son of the city's master Joh Fredersen, lives in the Eternal Gardens \u2014 a paradise untouched by labor. But when a mysterious woman named Maria brings the workers' children to glimpse this forbidden world, Freder's eyes are opened.

CHAPTER 2: THE REVOLUTION BEGINS

Deep in the bowels of the city, the Heart Machine explodes. Workers scramble. Freder, disguised as a laborer, witnesses the brutality firsthand. In a fever dream, he sees the machine transform into Moloch \u2014 an ancient god devouring its worshippers.

Meanwhile, the mad inventor Rotwang reveals his masterpiece: a robot built in the image of his lost love. When Joh Fredersen orders the robot to impersonate Maria and discredit her movement, chaos erupts.

CHAPTER 3: THE FLOOD

The workers, deceived by the false Maria, destroy the Heart Machine. Water floods the workers' city below. The real Maria, with Freder, rescues the children. But the mob, believing Maria a witch, hunts her through the cathedral.

On the rooftop, Rotwang battles Freder as lightning illuminates the gothic spires. The false Maria is burned at the stake, revealing her metallic skeleton. Maria prevails. The Heart Machine is rebuilt.

EPILOGUE: THE MEDIATOR

Standing before the cathedral, Freder unites the Head (his father) and the Hands (the workers) \u2014 completing the prophecy: "The mediator between brain and muscle must be the Heart."`;

export function StageScript() {
  const { projects, currentProjectId } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  const scenes = project?.scenes ?? SAMPLE_SCENES;
  const script = project?.script || SCRIPT;

  return (
    <motion.div className="flex h-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="w-[360px] flex flex-col"
        style={{
          borderRight: "1px solid rgba(30,30,50,0.5)",
          background: "linear-gradient(180deg, rgba(6,6,16,0.5), rgba(8,8,15,0.3))",
        }}
      >
        <div className="px-4 py-3" style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}>
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Scenes ({scenes.length})</span>
        </div>
        <ScrollArea className="h-[calc(100%-44px)]">
          <div className="p-2 space-y-1">
            {scenes.map((scene, i) => (
              <motion.div
                key={scene.id}
                className="flex items-start gap-2 px-3 py-2.5 rounded-lg transition-all cursor-pointer group"
                style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(30,30,50,0.4)",
                }}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                whileHover={{
                  x: 4,
                  borderColor: "rgba(124,58,237,0.15)",
                  background: "rgba(124,58,237,0.03)",
                }}
              >
                <GripVertical size={12} className="mt-0.5 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <Clapperboard size={11} className="text-accent-purple-soft shrink-0" />
                    <span className="text-xs font-medium text-text-primary truncate">{scene.title}</span>
                    {scene.importance > 0.9 && <Star size={10} style={{ color: "#F59E0B", fill: "#F59E0B" }} className="shrink-0" />}
                  </div>
                  <p className="text-[11px] text-text-secondary leading-relaxed line-clamp-2">{scene.description}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[10px] font-mono text-accent-blue-soft flex items-center gap-1">
                      <Clock size={9} />{scene.timestamp}
                    </span>
                    <div className="h-1 flex-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.04)" }}>
                      <motion.div
                        className="h-full rounded-full"
                        style={{
                          background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
                          width: `${scene.importance * 100}%`,
                        }}
                        initial={{ width: 0 }}
                        animate={{ width: `${scene.importance * 100}%` }}
                        transition={{ duration: 0.6, delay: 0.2 + i * 0.05 }}
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </ScrollArea>
      </div>
      <div className="flex-1 flex flex-col">
        <div className="px-6 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}>
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Script</span>
          <div className="flex items-center gap-1 text-[10px] text-text-muted">
            <span>Metropolis Recap</span>
            <span className="w-1 h-1 rounded-full" style={{ background: "#7C3AED" }} />
            <span>~15 min estimated</span>
          </div>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-8 max-w-2xl mx-auto">
            <div className="text-sm text-text-secondary leading-relaxed space-y-4 font-mono whitespace-pre-wrap">
              {script.split("\n\n").map((para, i) => (
                <motion.p
                  key={i}
                  className="rounded-lg px-2 py-1 -mx-2 transition-colors cursor-text"
                  style={{ color: "#9090B0" }}
                  whileHover={{
                    background: "rgba(124,58,237,0.04)",
                    color: "#E8E8F0",
                  }}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 + i * 0.05 }}
                >
                  {para}
                </motion.p>
              ))}
            </div>
          </div>
        </ScrollArea>
      </div>
    </motion.div>
  );
}
