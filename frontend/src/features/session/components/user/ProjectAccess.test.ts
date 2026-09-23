// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ProjectAccess from './ProjectAccess.vue'

describe('project access visibility', () => {
  it('distinguishes missing data from an empty assignment list', () => {
    expect(mount(ProjectAccess, { props: { user: {}, compact: true } }).text()).toContain(
      'unavailable'
    )
    expect(
      mount(ProjectAccess, { props: { user: { project_access: [] }, compact: true } }).text()
    ).toContain('No project roles assigned')
  })
  it('explains superuser access even without explicit assignments', () => {
    const wrapper = mount(ProjectAccess, {
      props: { user: { is_superuser: true, is_active: false, project_access: [] }, compact: true }
    })
    expect(wrapper.text()).toContain('All projects and applications')
    expect(wrapper.text()).toContain('Account inactive')
    expect(wrapper.text()).not.toContain('No project roles')
  })
})
