import { describe, expect, it } from 'vitest'
import { getPaginatedResults, isPaginatedResponse } from '@/shared/services/pagination'

describe('canonical pagination contract', () => {
  it('accepts the bounded DRF response shape', () => {
    const payload = { count: 1, next: null, previous: null, results: [{ id: 1 }] }

    expect(isPaginatedResponse(payload)).toBe(true)
    expect(getPaginatedResults<{ id: number }>(payload)).toEqual([{ id: 1 }])
  })

  it('does not adapt a retired top-level list response', () => {
    expect(getPaginatedResults([{ id: 1 }])).toEqual([])
  })
})
