import { describe, expect, it } from 'vitest'

import manifestSource from '../../../public/app/manifest.webmanifest?raw'
import serviceWorkerSource from '../../../public/app/sw.js?raw'

describe('PWA static contracts', () => {
  it('declares an app-scoped standalone manifest with standard and maskable icons', () => {
    const manifest = JSON.parse(manifestSource)

    expect(manifest.display).toBe('standalone')
    expect(manifest.start_url).toBe('/app/')
    expect(manifest.scope).toBe('/app/')
    expect(manifest.icons).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ sizes: '192x192', type: 'image/png', purpose: 'any' }),
        expect.objectContaining({ sizes: '512x512', type: 'image/png', purpose: 'any' }),
        expect.objectContaining({ sizes: '512x512', purpose: 'maskable' })
      ])
    )
  })

  it('keeps authenticated API traffic outside the service worker cache', () => {
    expect(serviceWorkerSource).toContain("url.pathname.startsWith('/api/')")
    expect(serviceWorkerSource).not.toMatch(/cache\.put\([^\n]*api/i)
  })
})
