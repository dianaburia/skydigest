import FloatingNav from "@/components/FloatingNav";
import IssueViewer from "@/components/IssueViewer";
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

  // The issue's own masthead is the page header; site chrome is just
  // the floating pill.
  return (
    <div className="issue-page">
      <IssueViewer html={latest.html} title={latest.title} />
      <FloatingNav />
    </div>
  );
}
