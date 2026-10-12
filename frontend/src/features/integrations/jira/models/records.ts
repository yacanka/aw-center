export interface IJiraTrackedIssue {
  id: string
  issue: string
  jira_issue_url?: string
  title: string
  owner: number | null
  assigned_users: number[]
  project_slugs: string[]
  version: number
  created_at: string
  updated_at: string
}
