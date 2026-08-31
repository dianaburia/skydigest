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
  const attachedDocRef = useRef<Document | null>(null);
  const [ask, setAsk] = useState<AskButton | null>(null);

  // A srcDoc iframe can finish loading before React hydrates (then onLoad
  // never fires — the effect covers it), but it also starts life with a
  // throwaway about:blank document that is later REPLACED by the real one
  // (listeners attached to it die with it — onLoad re-attaches). So: attach
  // from both places, keyed by the actual document instance.
  function attachListeners() {
    const doc = iframeRef.current?.contentDocument;
    const win = iframeRef.current?.contentWindow;
    if (!doc || !win || !doc.body || attachedDocRef.current === doc) return;
    attachedDocRef.current = doc;

    // On touch screens the native selection menu (Copy/Look Up) pops up
    // above the selection, so our button goes below it there.
    const coarsePointer = window.matchMedia("(pointer: coarse)").matches;

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
      const width = iframeRef.current?.clientWidth ?? 0;
      const height = iframeRef.current?.clientHeight ?? 0;
      const above = rect.top - 44;
      const below = Math.min(rect.bottom + 12, height - 52);
      setAsk({
        top: coarsePointer || above < 6 ? below : above,
        left: Math.min(Math.max(rect.left + rect.width / 2, 80), width - 80),
        text,
      });
    };

    // selectionchange covers mouse, keyboard AND touch selection (long-press
    // and handle-dragging fire no mouse events); debounced so the button
    // doesn't flicker while the selection is still being adjusted.
    let debounce: number | undefined;
    doc.addEventListener("selectionchange", () => {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(update, 250);
    });
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
          // pointerdown, not click: on mobile a tap first collapses the
          // selection, which would unmount the button before click fires.
          onPointerDown={(e) => {
            e.preventDefault();
            openChat();
          }}
        >
          Ask about this →
        </button>
      )}
    </div>
  );
}
