import Link from "next/link";
import { getIssue, getIssues } from "@/lib/api";

// Render on every request: a new issue lands weekly and the front page
// must always show the latest one.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const issues = await getIssues();
  const latest = issues.length > 0 ? await getIssue(issues[0].issue_date) : null;

  if (!latest) {
    return (
      <main className="archive">
        <h1>Observatory</h1>
        <p className="empty">No issues yet — the first one arrives on Saturday.</p>
      </main>
    );
  }

  return (
    <div className="issue-page">
      <header className="issue-header">
        <span className="brand">Observatory</span>
        <span className="issue-header-title">{latest.title}</span>
        <Link className="archive-link" href="/issues">
          Past issues →
        </Link>
      </header>
      <iframe className="issue-frame" srcDoc={latest.html} title={latest.title} />
    </div>
  );
}
