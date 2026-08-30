import Link from "next/link";
import { formatIssueDate, getIssues } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ArchivePage() {
  const issues = await getIssues();

  return (
    <main className="archive">
      <h1>Observatory</h1>
      <p className="tagline">
        All issues, newest first. <Link href="/">Latest issue →</Link>{" "}
        <Link href="/chat">Ask the archive →</Link>
      </p>
      {issues.length === 0 ? (
        <p className="empty">No issues yet — the first one arrives on Saturday.</p>
      ) : (
        <ul className="issue-list">
          {issues.map((issue) => (
            <li key={issue.issue_date}>
              <Link href={`/issues/${issue.issue_date}`}>
                <span className="issue-date">{formatIssueDate(issue.issue_date)}</span>
                <span className="issue-title">{issue.title}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
