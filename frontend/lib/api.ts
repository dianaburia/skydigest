// Thin client for the Observatory FastAPI backend.
// Pages call these functions instead of fetching URLs themselves,
// mirroring the repository layer on the backend.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface IssueSummary {
  issue_date: string; // "YYYY-MM-DD"
  title: string;
}

export interface Issue extends IssueSummary {
  html: string; // full self-contained HTML document of the issue
}

export async function getIssues(): Promise<IssueSummary[]> {
  const res = await fetch(`${API_URL}/issues`);
  if (!res.ok) {
    throw new Error(`GET /issues failed with ${res.status}`);
  }
  return res.json();
}

export async function getIssue(date: string): Promise<Issue | null> {
  const res = await fetch(`${API_URL}/issues/${date}`);
  if (res.status === 404 || res.status === 422) {
    return null; // unknown or malformed date → let the page render a 404
  }
  if (!res.ok) {
    throw new Error(`GET /issues/${date} failed with ${res.status}`);
  }
  return res.json();
}

export function formatIssueDate(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}
