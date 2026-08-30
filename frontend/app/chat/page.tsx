"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { askQuestion, Source } from "@/lib/api";

interface ChatMessage {
  role: "user" | "bot" | "error";
  text: string;
  sources?: Source[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setLoading(true);
    try {
      const res = await askQuestion(question);
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: res.answer, sources: res.sources },
      ]);
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
      <header className="issue-header">
        <span className="brand">Observatory</span>
        <span className="issue-header-title">Ask the archive</span>
        <nav className="header-nav">
          <Link href="/">Latest issue</Link>
          <Link href="/issues">Past issues</Link>
        </nav>
      </header>
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-hint">
            Ask anything about the past weeks of astronomy news and papers —
            answers come with links to the sources.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role}`}>
            {m.text}
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
        {loading && (
          <div className="bubble bubble-bot bubble-thinking">Thinking…</div>
        )}
        <div ref={bottomRef} />
      </div>
      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. What is the Einstein Probe?"
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
