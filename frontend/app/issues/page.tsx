import Link from "next/link";
import Masthead from "@/components/Masthead";
import { formatIssueDate, getIssues } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ArchivePage() {
  const issues = await getIssues();

  return (
    <>
      <Masthead />
      <main className="archive">
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
    </>
  );
}
