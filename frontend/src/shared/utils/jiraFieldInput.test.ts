import { describe, expect, it } from 'vitest'
import { jiraInputToken, resolveJiraFieldInputType } from './jiraFieldInput'

describe('JIRA field inputs', () => {
  it.each([
    ['boolean', 'boolean'],
    ['datetime', 'datetime'],
    ['integer', 'number'],
    ['user', 'person'],
    ['date', 'date'],
    ['object', 'unsupported']
  ])('uses the %s schema', (type, expected) => {
    expect(
      resolveJiraFieldInputType({ id: 'customfield_123', name: 'Field', schema: { type } })
    ).toBe(expected)
  })

  it('extracts stable references without stringifying objects', () => {
    expect(jiraInputToken({ id: '12', value: 'Review' })).toBe('12')
    expect(jiraInputToken({ accountId: 'account-1' })).toBe('account-1')
    expect(jiraInputToken({ unknown: 'value' })).toBeNull()
    expect(jiraInputToken(0)).toBe(0)
  })
})
