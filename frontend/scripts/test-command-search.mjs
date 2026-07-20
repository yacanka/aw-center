import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildNavigationCommands,
  mergeRecentCommand,
  normalizeSearchText,
  prioritizeRecentCommands,
  searchNavigationCommands
} from '../src/services/commandSearch.ts'

const sources = [
  { label: 'Home', key: '/home', name: 'home' },
  {
    label: 'Documents',
    key: '/documents',
    children: [
      { label: 'Translator', key: '/translator', name: 'translator' },
      { label: 'Disabled', key: '/disabled', disabled: true }
    ]
  },
  { key: 'divider', type: 'divider' },
  { label: 'Powerpoint Gallery', key: '/pptxGallery', name: 'pptxgallery' }
]

test('flattens only navigable enabled leaves', () => {
  const commands = buildNavigationCommands(sources)
  assert.deepEqual(
    commands.map(({ path }) => path),
    ['/home', '/translator', '/pptxGallery']
  )
  assert.equal(commands[1].category, 'Documents')
})

test('matches Turkish aliases and accent-independent text', () => {
  const commands = buildNavigationCommands(sources)
  const workflowCommands = buildNavigationCommands([{ label: 'Job Center', key: '/jobs' }])
  assert.equal(searchNavigationCommands(commands, 'çeviri')[0].path, '/translator')
  assert.equal(searchNavigationCommands(workflowCommands, 'otomasyon')[0].path, '/jobs')
  assert.equal(normalizeSearchText('İşlem Çözümü'), 'islem cozumu')
})

test('tolerates a small typo while preferring exact matches', () => {
  const commands = buildNavigationCommands(sources)
  assert.equal(searchNavigationCommands(commands, 'tranlator')[0].path, '/translator')
  assert.equal(searchNavigationCommands(commands, 'home')[0].path, '/home')
  assert.equal(
    searchNavigationCommands(buildNavigationCommands([{ label: 'Pdf', key: '/pdf' }]), 'ddf')
      .length,
    0
  )
})

test('prioritizes and updates bounded recent history', () => {
  const commands = buildNavigationCommands(sources)
  const ordered = prioritizeRecentCommands(commands, ['/translator', '/missing'])
  assert.equal(ordered[0].path, '/translator')
  assert.deepEqual(mergeRecentCommand(['/home', '/translator'], '/translator', 2), [
    '/translator',
    '/home'
  ])
})

test('respects the result limit', () => {
  const commands = buildNavigationCommands(sources)
  const manyCommands = buildNavigationCommands(
    Array.from({ length: 40 }, (_, index) => ({ label: `Tool ${index}`, key: `/tool-${index}` }))
  )
  assert.equal(searchNavigationCommands(commands, '', 2).length, 2)
  assert.equal(searchNavigationCommands(manyCommands, '', 10_000).length, 25)
})
