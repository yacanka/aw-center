import { expect, it } from 'vitest'
import { serializeCompdocFilters } from './table'

it('serializes name-based Panel and ATA independently while preserving canonical panel ID filters', () => {
  expect(serializeCompdocFilters({ panel: ['Systems'], ata: ['27-00'] })).toEqual({
    panel_name: ['Systems'],
    ata: ['27-00']
  })
  expect(serializeCompdocFilters({ panel: [1, 2], ata: ['27-00'] })).toEqual({
    panel: [1, 2],
    ata: ['27-00']
  })
})
