export const API_PATHS = {
  doors: 'integrations/doors',
  teamcenter: 'integrations/teamcenter',
  ddf: 'tools/ddf',
  docproof: 'integrations/docproof',
  excel: 'tools/excel',
  jiraSession: 'integrations/jira/session',
  media: 'tools/media',
  outlook: 'tools/outlook',
  pdf: 'tools/pdf',
  presentations: 'tools/presentations',
  word: 'tools/word'
} as const

/** Return the canonical project-scoped API collection path. */
export function projectApiPath(project: string, ...segments: Array<string | number>): string {
  return collectionPath('projects', project, ...segments)
}

/** Return the canonical compliance-document collection path for a project. */
export function compdocCollectionPath(project: string): string {
  return projectApiPath(project, 'compliance-documents')
}

/** Return one canonical compliance-document path. */
export function compdocDocumentPath(project: string, documentId: string): string {
  return projectApiPath(project, 'compliance-documents', documentId).replace(/\/$/, '')
}

/** Return a canonical project-organization collection path. */
export function organizationPath(project: string, ...segments: Array<string | number>): string {
  return projectApiPath(project, 'organization', ...segments)
}

function collectionPath(...segments: Array<string | number>): string {
  return `${segments.map((segment) => encodeURIComponent(String(segment))).join('/')}/`
}
