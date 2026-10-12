import { apiClient } from '@/shared/api/http'
import type { ISubtaskListItem } from '../models/jira'

export interface SavedJiraLists {
  lists: ISubtaskListItem[]
  version: number
}

/** Reject malformed saved content instead of silently replacing it with an empty list. */
export function parseSavedJiraLists(value: unknown): SavedJiraLists {
  if (!value || typeof value !== 'object') throw new Error('Saved JIRA lists are invalid.')
  const data = value as Partial<SavedJiraLists>
  if (
    !Number.isSafeInteger(data.version) ||
    Number(data.version) < 0 ||
    !Array.isArray(data.lists)
  ) {
    throw new Error('Saved JIRA lists are invalid.')
  }
  for (const list of data.lists) {
    if (
      !list ||
      typeof list !== 'object' ||
      typeof list.title !== 'string' ||
      !Array.isArray(list.list) ||
      list.list.some((row) => !row || typeof row !== 'object' || Array.isArray(row)) ||
      (list.fields !== undefined &&
        (!Array.isArray(list.fields) ||
          list.fields.some(
            (field) => !field || typeof field.id !== 'string' || typeof field.name !== 'string'
          )))
    ) {
      throw new Error('Saved JIRA list content is invalid. It has not been replaced.')
    }
  }
  return { lists: structuredClone(data.lists), version: data.version as number }
}

export async function fetchSavedJiraLists(): Promise<SavedJiraLists> {
  return parseSavedJiraLists((await apiClient.get('integrations/jira/subtasks/saved-lists/')).data)
}

export async function saveJiraLists(payload: SavedJiraLists): Promise<SavedJiraLists> {
  return parseSavedJiraLists(
    (await apiClient.put('integrations/jira/subtasks/saved-lists/', payload)).data
  )
}
