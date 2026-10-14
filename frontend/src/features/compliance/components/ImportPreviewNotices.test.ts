// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ImportPreviewNotices from './ImportPreviewNotices.vue'
import type { ImportPreview } from '../api/compdocImports'
it('keeps long import notices closed until requested and lists each entry separately', async () => {
  const wrapper = mount(ImportPreviewNotices, {
    props: {
      preview: {
        unmapped_columns: ['Unused 1', 'Unused 2'],
        status_changes: [
          { value: 'new_1', label: 'New status 1' },
          { value: 'new_2', label: 'New status 2' }
        ],
        panel_changes: [{ ata: '29-00', old_name: null, new_name: 'Hydraulics', action: 'create' }]
      } as ImportPreview
    }
  })
  expect(wrapper.findAll('li')).toHaveLength(0)
  const headers = wrapper.findAll('.n-collapse-item__header-main')
  expect(headers.map((header) => header.text())).toEqual([
    'There are unmapped columns',
    'New project statuses',
    'Project panel changes'
  ])
  await headers[0].trigger('click')
  await flushPromises()
  expect(wrapper.findAll('li').map((row) => row.text())).toEqual(['Unused 1', 'Unused 2'])
  await headers[1].trigger('click')
  await flushPromises()
  expect(wrapper.findAll('li').map((row) => row.text())).toEqual([
    'Unused 1',
    'Unused 2',
    'New status 1',
    'New status 2'
  ])
  await headers[2].trigger('click')
  await flushPromises()
  expect(wrapper.findAll('li').at(-1)?.text()).toContain('Create 29-00: Hydraulics')
  wrapper.unmount()
})
