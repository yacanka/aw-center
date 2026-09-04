import { describe, expect, it } from 'vitest'
import { toSubtaskRequest } from './subtaskItems'
import type { ISubtaskItem } from './jira'

describe('main-branch saved subtask list compatibility', () => {
  it('maps dynamic built-ins while retaining custom columns and labels', () => {
    const item: ISubtaskItem = {
      summary: 'Review',
      assignee: 'reviewer',
      fields: {
        description: 'Review details',
        duedate: '2026-09-30',
        customfield_10001: ['Option A'],
        labels: ['review']
      }
    }
    const original = JSON.stringify(item)
    expect(toSubtaskRequest(item)).toEqual({
      summary: 'Review',
      description: 'Review details',
      assignee: 'reviewer',
      due_date: '2026-09-30',
      fields: { customfield_10001: ['Option A'], labels: ['review'] }
    })
    expect(JSON.stringify(item)).toBe(original)
  })

  it('accepts older rows without a fields object and retains their description', () => {
    expect(toSubtaskRequest({ summary: 'Review', description: 'Details' })).toEqual({
      summary: 'Review',
      description: 'Details',
      assignee: '',
      due_date: null,
      fields: {}
    })
  })

  it('preserves zero numeric values and empty rows for server-side validation', () => {
    expect(toSubtaskRequest({ fields: { customfield_10002: 0 } })).toEqual({
      summary: '',
      description: '',
      assignee: '',
      due_date: null,
      fields: { customfield_10002: 0 }
    })
  })
})
