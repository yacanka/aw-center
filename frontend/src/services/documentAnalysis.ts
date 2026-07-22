import axios from 'axios'

export interface CustomAnalysisCheck {
  id: string
  question: string
}

interface CustomAnalysisCheckList {
  results: CustomAnalysisCheck[]
}

/** Load the current user's saved document-analysis questions. */
export async function fetchCustomAnalysisChecks(): Promise<CustomAnalysisCheck[]> {
  const response = await axios.get<CustomAnalysisCheckList>('/word/analysis-checks/')
  return response.data.results
}

/** Save one custom question in the current user's profile. */
export async function createCustomAnalysisCheck(question: string): Promise<CustomAnalysisCheck> {
  const response = await axios.post<CustomAnalysisCheck>('/word/analysis-checks/', { question })
  return response.data
}

/** Delete one custom question owned by the current user. */
export async function deleteCustomAnalysisCheck(identifier: string): Promise<void> {
  await axios.delete(`/word/analysis-checks/${identifier}/`)
}

/** Convert a persisted custom identifier to an analysis selection value. */
export function customAnalysisCheckValue(identifier: string): string {
  return `custom:${identifier}`
}
