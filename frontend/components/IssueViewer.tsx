"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// Selections longer than this are truncated before being sent to the chat:
// together with the user's question they must fit the API's question limit.
const MAX_CONTEXT_CHARS = 400;

interface AskButton {
  top: number;
  left: number;
  text: string;
}

// Renders an issue's self-contained HTML in an iframe and adds
// highlight-to-ask: selecting text inside the issue shows a floating
// "Ask about this" button that opens the chat with the selection as context.
// The iframe is created via srcDoc, so it is same-origin and its document
// is fully accessible from here.
export default function IssueViewer({ html, title }: { html: string; title: string }) {
  const router = useRouter();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const attachedRef = useRef(false);
  const [ask, setAsk] = useState<AskButton | null>(null);

  // A srcDoc iframe can finish loading before React hydrates, in which case
  // the onLoad prop never fires — so attach is also tried from an effect.
  function attachListeners() {
    if (attachedRef.current) return;
    const doc = iframeRef.current?.contentDocument;
    const win = iframeRef.current?.contentWindow;
    if (!doc || !win || !doc.body) return;
    attachedRef.current = true;

    const update = () => {
      const selection = doc.getSelection();
      const text = selection?.toString().trim() ?? "";
      if (!selection || selection.isCollapsed || text.length < 3) {
        setAsk(null);
        return;
      }
      // The iframe fills its wrapper, so iframe-viewport coordinates are
      // wrapper coordinates: the button can be positioned directly.
      const rect = selection.getRangeAt(0).getBoundingClientRect();
      setAsk({
        top: Math.max(rect.top - 44, 6),
        left: rect.left + rect.width / 2,
        text,
      });
    };

    // A tick after mouseup/keyup the selection object is final.
    doc.addEventListener("mouseup", () => setTimeout(update, 0));
    doc.addEventListener("keyup", () => setTimeout(update, 0));
    // Scrolling the issue would leave the button floating over nothing.
    win.addEventListener("scroll", () => setAsk(null));
  }

  useEffect(() => {
    attachListeners();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openChat() {
    if (!ask) return;
    const context = ask.text.slice(0, MAX_CONTEXT_CHARS);
    router.push(`/chat?context=${encodeURIComponent(context)}`);
  }

  return (
    <div className="issue-viewer">
      <iframe
        ref={iframeRef}
        className="issue-frame"
        srcDoc={html}
        title={title}
        onLoad={attachListeners}
      />
      {ask && (
        <button
          type="button"
          className="ask-button"
          style={{ top: ask.top, left: ask.left }}
          onClick={openChat}
        >
          Ask about this →
        </button>
      )}
    </div>
  );
}
