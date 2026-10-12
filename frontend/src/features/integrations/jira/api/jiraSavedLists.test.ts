import { describe, expect, it } from 'vitest'
import { parseSavedJiraLists } from './jiraSavedLists'

describe('saved JIRA content contract', () => {
  it('preserves drafts and optional metadata without changing the source', () => {
    const source = { lists: [{ title: 'Draft', list: [{ summary: '' }] }], version: 2 }
    const result = parseSavedJiraLists(source)
    result.lists[0].title = 'Edited'
    expect(source.lists[0].title).toBe('Draft')
    expect(result.version).toBe(2)
  })
  it.each([
    {},
    { lists: [], version: -1 },
    { lists: [], version: true },
    { lists: [{ title: 'Invalid', list: [null] }], version: 1 },
    { lists: [{ title: 'Invalid', list: [], fields: {} }], version: 1 }
  ])('rejects malformed server content instead of replacing it with an empty list', (value) => {
    expect(() => parseSavedJiraLists(value)).toThrow()
  })
})
