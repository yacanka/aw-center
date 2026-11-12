import { expect, it } from 'vitest'
import { createEmptyCompdoc } from './compdocCatalog'
import { buildCompdocCreatePayload, buildCompdocUpdatePayload } from './compdocPayload'

it('carries a named ATA-less panel when no catalog ID exists yet', () => {
  const document = { ...createEmptyCompdoc(), panel_name: 'Systems' }
  expect(buildCompdocCreatePayload(document)).toMatchObject({
    panel: null,
    panel_name: 'Systems',
    ata: null
  })
  expect(buildCompdocUpdatePayload(document)).toMatchObject({ panel_name: 'Systems' })
})

it('leaves catalog identity authoritative when a panel ID is selected', () => {
  const document = { ...createEmptyCompdoc(), panel: 4, panel_name: 'Systems', ata: '27-00' }
  expect(buildCompdocCreatePayload(document)).not.toHaveProperty('panel_name')
})
