import { describe, expect, it } from 'vitest'
import {
  effectivePermissions,
  permissionDescription,
  roleDescription,
  isCriticalRole
} from './userAccess'

const view = {
  id: 1,
  name: 'Can view user',
  codename: 'view_user',
  content_type: { app_label: 'auth' }
}
const change = { id: 2, codename: 'change_user', content_type: { app_label: 'auth' } }

describe('user access summary', () => {
  it('deduplicates direct and inherited permissions without changing assignments', () => {
    const user = {
      permissions: [view],
      group_details: [{ name: 'Editors', permissions: [view, change] }]
    }
    expect(effectivePermissions(user)).toEqual([change, view])
    expect(user.permissions).toEqual([view])
  })
  it('handles users without assignments', () => {
    expect(effectivePermissions({})).toEqual([])
  })
  it('explains user administration and scopes fallback descriptions', () => {
    expect(permissionDescription(change)).toContain('Only superusers')
    expect(
      permissionDescription({
        name: 'Can export',
        codename: 'export',
        content_type: { app_label: 'custom' }
      })
    ).toContain('project and record access rules still apply')
  })
})

it('explains critical roles from their permissions rather than their names', () => {
  expect(isCriticalRole({ name: 'Readers', permissions: [view] })).toBe(true)
  expect(roleDescription({ permissions: [change] })).toContain('Sensitive access')
  expect(roleDescription({ permissions: [] })).toContain('Project roles are listed separately')
})
