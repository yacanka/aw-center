import { describe, expect, it, vi } from 'vitest'
import {
  captureInitialPasswordResetCapability,
  consumePasswordResetCapability,
  takePasswordResetCapability
} from './passwordResetCapability'

describe('consumePasswordResetCapability', () => {
  it('returns and immediately scrubs a complete fragment capability', () => {
    const replaceState = vi.fn()

    const capability = consumePasswordResetCapability(
      {
        hash: '#uid=MQ&token=abc-123',
        pathname: '/app/login',
        search: '?redirect=%2Fhome'
      },
      { state: { navigation: 1 }, replaceState }
    )

    expect(capability).toEqual({ uid: 'MQ', token: 'abc-123' })
    expect(replaceState).toHaveBeenCalledOnce()
    expect(replaceState).toHaveBeenCalledWith({ navigation: 1 }, '', '/app/login?redirect=%2Fhome')
  })

  it('scrubs a partial sensitive fragment but does not authorize reset', () => {
    const replaceState = vi.fn()

    const capability = consumePasswordResetCapability(
      { hash: '#token=incomplete', pathname: '/app/login', search: '' },
      { state: null, replaceState }
    )

    expect(capability).toBeNull()
    expect(replaceState).toHaveBeenCalledWith(null, '', '/app/login')
  })

  it('leaves unrelated fragments untouched', () => {
    const replaceState = vi.fn()

    const capability = consumePasswordResetCapability(
      { hash: '#section', pathname: '/app/login', search: '' },
      { state: null, replaceState }
    )

    expect(capability).toBeNull()
    expect(replaceState).not.toHaveBeenCalled()
  })

  it('captures the initial login capability before routing and transfers it once', () => {
    const replaceState = vi.fn()
    captureInitialPasswordResetCapability(
      { hash: '#uid=Mg&token=once-only', pathname: '/app/login', search: '' },
      { state: null, replaceState }
    )

    expect(replaceState).toHaveBeenCalledWith(null, '', '/app/login')
    expect(takePasswordResetCapability()).toEqual({ uid: 'Mg', token: 'once-only' })
    expect(takePasswordResetCapability()).toBeNull()
  })
})
