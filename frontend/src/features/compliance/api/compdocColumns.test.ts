// @vitest-environment jsdom
import { beforeEach, expect, it } from 'vitest'
import { normalizeCompdocFields } from './compdocContract'
import { readCompdocColumnSettings, saveCompdocColumnSettings } from './compdocColumns'

const fields = normalizeCompdocFields({
  schema_version: 4,
  fields: [
    { key: 'name', label: 'Name', required: true, read_only: false },
    { key: 'number', label: 'Number', required: false, read_only: false }
  ]
}).fields

beforeEach(() => localStorage.clear())

it('resets only this project column layout after a schema change', () => {
  saveCompdocColumnSettings('ozgur', 3, [
    { key: 'name', width: 250, sorter: false, filter: false, ellipsis: false }
  ])
  localStorage.setItem('theme', 'dark')
  saveCompdocColumnSettings('other', 4, [])
  expect(readCompdocColumnSettings('ozgur', fields, 4).map((field) => field.key)).toEqual([
    'name',
    'number'
  ])
  expect(localStorage.getItem('theme')).toBe('dark')
  expect(localStorage.getItem('compdocs>column_settings>other')).not.toBeNull()
})

it('preserves deliberately hidden columns for the current schema', () => {
  saveCompdocColumnSettings('ozgur', 4, [
    { key: 'name', width: 250, sorter: false, filter: false, ellipsis: false }
  ])
  expect(readCompdocColumnSettings('ozgur', fields, 4).map((field) => field.key)).toEqual(['name'])
})
