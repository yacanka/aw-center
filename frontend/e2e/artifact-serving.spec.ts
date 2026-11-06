import { expect, test } from '@playwright/test'

test('serves the compiled SPA and public assets at the Django URL boundaries', async ({
  request
}) => {
  const response = await request.get('/app/login')
  expect(response.status()).toBe(200)
  expect(new URL(response.url()).pathname).toBe('/app/login')
  const html = await response.text()
  const script = html.match(/<script[^>]+src="([^"]+)"/)
  expect(script?.[1]).toMatch(/^\/core\/assets\/.+\.js$/)
  expect(html).not.toContain('/@vite/client')

  const javascript = await request.get(script![1])
  expect(javascript.status()).toBe(200)
  expect(javascript.headers()['content-type']).toContain('javascript')

  const deepLink = await request.get('/app/compdocs/aesa?tab=documents')
  expect(deepLink.status()).toBe(200)
  expect(new URL(deepLink.url()).pathname).toBe('/app/compdocs/aesa')
  expect(await deepLink.text()).toBe(html)

  const manifest = await request.get('/app/manifest.webmanifest')
  expect(manifest.status()).toBe(200)
  expect(await manifest.json()).toMatchObject({ start_url: '/app/', scope: '/app/' })

  const icon = await request.get('/app/icons/pwa-192.png')
  expect(icon.status()).toBe(200)
  expect(icon.headers()['content-type']).toContain('image/png')

  const serviceWorker = await request.get('/app/sw.js')
  expect(serviceWorker.status()).toBe(200)
  expect(serviceWorker.headers()['content-type']).toContain('javascript')
})
