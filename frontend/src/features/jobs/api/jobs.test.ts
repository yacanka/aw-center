import { describe, expect, it } from 'vitest'
import { isActiveJobStatus, isFailedJobStatus } from '@/features/jobs/api/jobs'

describe('job terminal-state policy', () => {
  it('treats reconciliation-required as terminal failure', () => {
    expect(isActiveJobStatus('reconciliation_required')).toBe(false)
    expect(isFailedJobStatus('reconciliation_required')).toBe(true)
  })
})
