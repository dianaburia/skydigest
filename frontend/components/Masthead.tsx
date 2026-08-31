import Link from "next/link";

// Newspaper-style nameplate for the utility pages (/issues, /chat),
// echoing the journal's own typography.
export default function Masthead() {
  return (
    <header className="masthead">
      <Link className="masthead-title" href="/">
        Observatory
      </Link>
      <nav className="masthead-nav">
        <Link href="/">Latest issue</Link>
        <span aria-hidden="true">·</span>
        <Link href="/issues">Archive</Link>
        <span aria-hidden="true">·</span>
        <Link href="/chat">Ask the archive</Link>
      </nav>
    </header>
  );
}
