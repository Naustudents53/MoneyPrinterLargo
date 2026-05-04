"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, Minimize2, Terminal } from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const SAMPLE_RESPONSES = [
  "I'll tighten scene 3 — the chase sequence should cut faster. Applying 0.8x spacing.",
  "That shot at 14:22 has better lighting. Swapped it in for the current clip.",
  "The narration at chapter 2 feels too slow. Regenerating with higher drama, 1.15x pace.",
  "Good call. I've added a slow fade from the title card into the first scene.",
  "The music swell should hit right at 8:45 — I'll adjust the crossfade to match.",
];

export function FloatingAIDirector() {
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSend = async () => {
    if (!input.trim()) return;
    setMessages((p) => [...p, { id: crypto.randomUUID(), role: "user", content: input }]);
    setInput("");
    setThinking(true);
    await new Promise((r) => setTimeout(r, 1200 + Math.random() * 800));
    setThinking(false);
    setMessages((p) => [
      ...p,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: SAMPLE_RESPONSES[Math.floor(Math.random() * SAMPLE_RESPONSES.length)],
      },
    ]);
  };

  if (minimized) {
    return (
      <motion.button
        className="fixed bottom-6 right-6 w-3 h-3 rounded-full z-50"
        style={{
          background: "linear-gradient(135deg, #E8A24F, #3B82F6)",
          boxShadow: "0 0 16px rgba(232,162,79,0.5)",
        }}
        onClick={() => setMinimized(false)}
        whileHover={{ scale: 2.5 }}
      />
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <AnimatePresence>
        {expanded && (
          <motion.div
            className="absolute bottom-16 right-0 w-[320px] overflow-hidden"
            style={{
              background: "linear-gradient(180deg, rgba(28,28,43,0.98), rgba(20,20,35,0.98))",
              border: "1px solid rgba(232,162,79,0.2)",
              borderRadius: "16px",
              boxShadow: "0 24px 64px rgba(0,0,0,0.6), 0 0 40px rgba(232,162,79,0.1)",
            }}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b"
              style={{ borderColor: "rgba(30,30,50,0.5)" }}
            >
              <span className="text-sm font-medium text-text-primary flex items-center gap-2">
                <Sparkles size={14} className="text-accent-purple-soft" />
                AI Director
              </span>
              <button
                onClick={() => setMinimized(true)}
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                <Minimize2 size={14} />
              </button>
            </div>

            {/* Messages */}
            <div className="h-52 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 && (
                <div className="text-xs text-text-muted text-center py-8">
                  <Terminal size={20} className="mx-auto mb-2 text-text-muted/50" />
                  <p>Ask the director anything.</p>
                </div>
              )}
              {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  className={`text-xs px-3 py-2.5 rounded-xl max-w-[85%] leading-relaxed ${
                    msg.role === "user"
                      ? "ml-auto"
                      : ""
                  }`}
                  style={
                    msg.role === "user"
                      ? {
                          background: "linear-gradient(135deg, rgba(232,162,79,0.15), rgba(96,165,250,0.08))",
                          border: "1px solid rgba(232,162,79,0.15)",
                          color: "#E8E8F0",
                        }
                      : {
                          background: "rgba(255,255,255,0.03)",
                          border: "1px solid rgba(30,30,50,0.5)",
                          color: "#9090B0",
                        }
                  }
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  {msg.content}
                </motion.div>
              ))}
              {thinking && (
                <div className="flex items-center gap-2 px-3 py-2 text-xs text-text-muted">
                  <div className="w-4 h-4 rounded-full border-2 border-accent-purple/20 border-t-accent-purple animate-spin" />
                  Working...
                </div>
              )}
            </div>

            {/* Input */}
            <div
              className="flex items-center gap-2 px-4 py-3 border-t"
              style={{ borderColor: "rgba(30,30,50,0.5)" }}
            >
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="e.g., make scene 3 more dramatic"
                className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
              />
              <motion.button
                onClick={handleSend}
                className="text-accent-purple-soft hover:text-accent-purple transition-colors disabled:opacity-30"
                whileTap={{ scale: 0.9 }}
                disabled={!input.trim()}
              >
                <Send size={16} />
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* FAB */}
      <motion.button
        className="w-12 h-12 rounded-full flex items-center justify-center relative overflow-hidden"
        style={{
          background: "linear-gradient(135deg, #E8A24F, #C47A28)",
          boxShadow: thinking
            ? "0 0 30px rgba(232,162,79,0.5)"
            : "0 0 20px rgba(232,162,79,0.3)",
          border: "1px solid rgba(232,162,79,0.3)",
        }}
        onClick={() => setExpanded(!expanded)}
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.92 }}
        animate={
          thinking
            ? {
                boxShadow: [
                  "0 0 20px rgba(232,162,79,0.3)",
                  "0 0 45px rgba(232,162,79,0.6)",
                  "0 0 20px rgba(232,162,79,0.3)",
                ],
              }
            : {}
        }
        transition={thinking ? { duration: 1.5, repeat: Infinity } : {}}
      >
        <Sparkles size={20} className="text-white" />
      </motion.button>
    </div>
  );
}
