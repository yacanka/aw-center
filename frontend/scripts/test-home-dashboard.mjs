import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import {
  buildWorkMetrics,
  integrationExceptions,
  recentSuccessfulJobs
} from '../src/services/homeDashboard.ts'

test('summarizes only active owner-scoped work states', () => {
  const metrics = buildWorkMetrics({
    available: true,
    active_workers: 1,
    counts: { awaiting_confirmation: 2, queued: 3, running: 4, cancel_requested: 1, failed: 9 }
  })

  assert.deepEqual(
    metrics.map(({ label, value }) => [label, value]),
    [
      ['Waiting for review', 2],
      ['Queued', 3],
      ['In progress', 5]
    ]
  )
})

test('selects bounded successful activity without exposing failed jobs', () => {
  const jobs = [
    { id: 'failed', status: 'failed' },
    { id: 'newest', status: 'succeeded' },
    { id: 'older', status: 'succeeded' }
  ]

  assert.deepEqual(
    recentSuccessfulJobs(jobs, 1).map(({ id }) => id),
    ['newest']
  )
})

test('keeps only configuration and live-health integration exceptions', () => {
  const integrations = [
    { id: 'ready', status: 'ready', health: { status: 'available' } },
    { id: 'config', status: 'attention' },
    { id: 'degraded', status: 'ready', health: { status: 'degraded' } },
    { id: 'checking', status: 'ready', health: { status: 'checking' } }
  ]

  assert.deepEqual(
    integrationExceptions(integrations).map(({ id }) => id),
    ['config', 'degraded']
  )
})

test('application home composes attention, work, quick access, and integration exceptions', async () => {
  const [home, mainView, commandPalette, jobs, integrations] = await Promise.all([
    readFile(new URL('../src/views/Home.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/MainView.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/navigation/CommandPalette.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/home/JobOverview.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/home/IntegrationExceptions.vue', import.meta.url), 'utf8')
  ])

  assert.match(home, /ActionCenter[\s\S]*JobOverview[\s\S]*QuickAccess[\s\S]*IntegrationExceptions/)
  assert.match(mainView, /provide\(MAIN_MENU_OPTIONS_KEY, menuOptions\)/)
  assert.match(commandPalette, /watch\(\(\) => route\.path, rememberVisitedCommand/)
  assert.match(jobs, /Promise\.all\(\[fetchJobs\(1, 20\), fetchJobSystemStatus\(\)\]\)/)
  assert.match(integrations, /fetchIntegrationCatalog\(true\)/)
})
