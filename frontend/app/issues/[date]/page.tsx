import Link from "next/link";
import { notFound } from "next/navigation";
import IssueViewer from "@/components/IssueViewer";
import { getIssue } from "@/lib/api";

export default async function IssuePage(props: PageProps<"/issues/[date]">) {
  const { date } = await props.params;
  const issue = await getIssue(date);
  if (!issue) {
    notFound();
  }

  // The issue html is a complete standalone document with its own inline
  // styles, so it is shown in an iframe to keep those styles isolated.
  return (
    <div className="issue-page">
      <header className="issue-header">
        <Link href="/issues">← All issues</Link>
        <span className="issue-header-title">{issue.title}</span>
      </header>
      <IssueViewer html={issue.html} title={issue.title} />
    </div>
  );
}
