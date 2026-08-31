"use client";

import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import Masthead from "@/components/Masthead";
import { askQuestionStream, Source } from "@/lib/api";

interface ChatMessage {
  role: "user" | "bot" | "error";
  text: string;
  context?: string; // highlighted issue passage this question was about
  sources?: Source[];
}

// useSearchParams needs a Suspense boundary on a prerendered page.
export default function ChatPage() {
  return (
    <Suspense>
      <Chat />
    </Suspense>
  );
}

function Chat() {
  // Highlight-to-ask lands here as /chat?context=<selected text>.
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [context, setContext] = useState<string | null>(
    () => searchParams.get("context"),
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;
    // With a highlighted passage attached, the API gets passage + question
    // in one string; the passage's own wording is a strong retrieval key.
    const fullQuestion = context
      ? `Regarding this passage from the journal: "${context}"\n\n${question}`
      : question;

    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question, context: context ?? undefined },
    ]);
    setContext(null); // the context is one-shot
    setLoading(true);

    // Grow the last bot bubble in place as pieces of the answer stream in;
    // the bubble is created on the first piece (until then "Thinking…" shows).
    const updateLast = (patch: (last: ChatMessage) => ChatMessage) =>
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last.role !== "bot") {
          return [...prev, patch({ role: "bot", text: "" })];
        }
        return [...prev.slice(0, -1), patch(last)];
      });

    try {
      await askQuestionStream(fullQuestion, {
        onDelta: (text) => updateLast((last) => ({ ...last, text: last.text + text })),
        onSources: (sources) => updateLast((last) => ({ ...last, sources })),
      });
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "error",
          text: err instanceof Error ? err.message : "Something went wrong.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-page">
      <Masthead />
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-hint">
            Ask anything about the past weeks of astronomy news and papers —
            answers come with links to the sources.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role}`}>
            {m.context && <blockquote className="bubble-quote">{m.context}</blockquote>}
            {m.role === "bot" ? <ReactMarkdown>{m.text}</ReactMarkdown> : m.text}
            {m.sources && m.sources.length > 0 && (
              <ul className="bubble-sources">
                {m.sources.map((s) => (
                  <li key={s.number}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer">
                      [{s.number}] {s.title}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
        {loading && messages[messages.length - 1]?.role === "user" && (
          <div className="bubble bubble-bot bubble-thinking">Thinking…</div>
        )}
        <div ref={bottomRef} />
      </div>
      {context && (
        <div className="context-chip">
          <span className="context-chip-text">Asking about: “{context}”</span>
          <button
            type="button"
            aria-label="Remove context"
            onClick={() => setContext(null)}
          >
            ×
          </button>
        </div>
      )}
      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            context
              ? "e.g. Tell me more about this"
              : "e.g. What is the Einstein Probe?"
          }
          maxLength={500}
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
