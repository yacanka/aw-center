import assert from 'node:assert/strict'
import test from 'node:test'
import {
  AUTHENTICATED_ACCESS,
  PUBLIC_ACCESS,
  filterNavigationByAccess,
  hasEffectivePermission,
  navigationAccessPolicy,
  resolveRouteAccess,
  safePostLoginPath
} from '../src/services/accessPolicy.ts'

const permission = (appLabel, codename) => ({ content_type: { app_label: appLabel }, codename })
const standardUser = { id: 7, is_active: true, permissions: [], group_details: [] }
const staffUser = { ...standardUser, id: 8, is_staff: true }
const superuser = { ...standardUser, id: 9, is_superuser: true }

test('denies anonymous protected routes and allows the explicit public policy', () => {
  assert.equal(resolveRouteAccess(AUTHENTICATED_ACCESS, null), 'login')
  assert.equal(resolveRouteAccess(PUBLIC_ACCESS, null), 'allow')
})

test('recognizes direct and group-derived Django permissions', () => {
  const directUser = { ...standardUser, permissions: [permission('ddf', 'view_ddf')] }
  const groupUser = {
    ...standardUser,
    group_details: [{ permissions: [permission('auth', 'view_user')] }]
  }
  assert.equal(hasEffectivePermission(directUser, 'ddf.view_ddf'), true)
  assert.equal(hasEffectivePermission(groupUser, 'auth.view_user'), true)
  assert.equal(hasEffectivePermission(groupUser, 'auth.delete_user'), false)
})

test('enforces granular user, DDF, Outlook Task, and developer policies', () => {
  const viewer = { ...standardUser, permissions: [permission('auth', 'view_user')] }
  const ddfViewer = { ...standardUser, permissions: [permission('ddf', 'view_ddf')] }
  const dccCreator = { ...standardUser, permissions: [permission('dcc', 'add_jira_dcc')] }
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/users'), viewer), 'allow')
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/ddfAssistant'), ddfViewer), 'allow')
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/outlook'), standardUser), 'forbidden')
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/outlook'), dccCreator), 'allow')
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/task/ecr'), dccCreator), 'allow')
  assert.equal(
    resolveRouteAccess(navigationAccessPolicy('/developer/doors'), standardUser),
    'forbidden'
  )
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/developer/doors'), staffUser), 'allow')
  assert.equal(resolveRouteAccess(navigationAccessPolicy('/users'), superuser), 'allow')
})

test('filters denied leaves and empty groups from navigation', () => {
  const menu = [
    { label: 'Home', key: '/home' },
    { label: 'Users', key: '/users' },
    { label: 'Developer', key: '/developer', children: [{ key: '/developer/doors' }] }
  ]
  assert.deepEqual(
    filterNavigationByAccess(menu, standardUser).map(({ key }) => key),
    ['/home']
  )
})

test('accepts only bounded internal post-login redirects', () => {
  assert.equal(safePostLoginPath('/jobs?page=2'), '/jobs?page=2')
  assert.equal(safePostLoginPath('//evil.example'), '/home')
  assert.equal(safePostLoginPath('https://evil.example'), '/home')
  assert.equal(safePostLoginPath('/login?redirect=/users'), '/home')
  assert.equal(safePostLoginPath(`/${'a'.repeat(600)}`), '/home')
})
