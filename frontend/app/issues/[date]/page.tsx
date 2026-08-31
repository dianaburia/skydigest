import { notFound } from "next/navigation";
import FloatingNav from "@/components/FloatingNav";
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
      <IssueViewer html={issue.html} title={issue.title} />
      <FloatingNav />
    </div>
  );
}
