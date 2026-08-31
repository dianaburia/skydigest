import Link from "next/link";

// Small floating pill in the corner of full-screen issue pages: the issue's
// own masthead is the page header, this is the only site chrome on top of it.
export default function FloatingNav() {
  return (
    <nav className="float-nav">
      <Link href="/issues">Issues</Link>
      <span aria-hidden="true">·</span>
      <Link href="/chat">Ask</Link>
    </nav>
  );
}
