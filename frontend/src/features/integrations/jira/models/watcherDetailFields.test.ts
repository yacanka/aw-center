import { describe, expect, it } from 'vitest'
import { selectWatcherDetailFields } from './watcherDetailFields'
const fields = [
  { id: 'customfield_45000', label: 'ECD number', value: 'ECD-1' },
  { id: 'customfield_45001', label: 'Revision', value: 'A' },
  { id: 'customfield_45002', label: 'DCC number', value: 'DCC-1' },
  { id: 'customfield_1', label: 'Panel', value: 'Safety' }
]
describe('Watcher detail field selection', () => {
  it('keeps the default document fields for a project without saved selection', () => {
    expect(selectWatcherDetailFields(fields, ['hys'], {}).map((field) => field.id)).toEqual([
      'customfield_45000',
      'customfield_45001',
      'customfield_45002'
    ])
  })
  it('honors an explicitly empty selection', () => {
    expect(selectWatcherDetailFields(fields, ['hys'], { hys: [] })).toEqual([])
  })
  it('unions multiple project selections without duplicates and ignores unavailable ids', () => {
    expect(
      selectWatcherDetailFields(fields, ['hys', 'aesa'], {
        hys: ['customfield_1', 'missing'],
        aesa: ['customfield_1', 'customfield_45001']
      }).map((field) => field.id)
    ).toEqual(['customfield_1', 'customfield_45001'])
  })
  it('applies defaults only for unsaved projects in a shared issue', () => {
    expect(
      selectWatcherDetailFields(fields, ['hys', 'aesa'], { hys: [] }).map((field) => field.id)
    ).toEqual(['customfield_45000', 'customfield_45001', 'customfield_45002'])
  })
})

it('uses component selections ahead of legacy projects and treats None as a separate scope', () => {
  expect(
    selectWatcherDetailFields(fields, ['hys'], { hys: ['customfield_45000'] }, ['Safety'], {
      'component:Safety': ['customfield_1']
    }).map((field) => field.id)
  ).toEqual(['customfield_1'])
  expect(selectWatcherDetailFields(fields, ['hys'], {}, [], { none: [] })).toEqual([])
})
