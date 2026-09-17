import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('@/shared/api/http', () => ({
  apiClient: { get: vi.fn(), patch: vi.fn() },
  isAuthenticationFailure: () => false
}))
vi.mock('@/shared/services/notify', () => ({
  notifyError: vi.fn(),
  notifySuccess: vi.fn(),
  notifyWarning: vi.fn()
}))
import { apiClient } from '@/shared/api/http'
import { createUserAdministrationController } from './userAdministrationController'

const page = (results: unknown[], next: string | null) => ({
  status: 200,
  data: { results, count: 2, next, previous: null }
})
describe('user administration catalogs', () => {
  beforeEach(() => vi.clearAllMocks())
  it('loads every permission page before enabling edits', async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce(page([{ id: 1 }], '/page2'))
      .mockResolvedValueOnce(page([{ id: 2 }], null))
    const controller = createUserAdministrationController()
    await controller.fetchPermissions()
    expect(controller.permissionsLoaded).toBe(true)
    expect(controller.getPermissions).toEqual([{ id: 1 }, { id: 2 }])
    expect(apiClient.get).toHaveBeenLastCalledWith('users/permissions/', {
      params: { page: 2, page_size: 200 }
    })
  })
  it('does not expose a partial catalog after a page fails', async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce(page([{ id: 1 }], '/page2'))
      .mockRejectedValueOnce(new Error('Unavailable'))
    const controller = createUserAdministrationController()
    await expect(controller.fetchGroups()).rejects.toThrow()
    expect(controller.groupsLoaded).toBe(false)
    expect(controller.getGroups).toEqual([])
  })
  it('keeps the displayed user unchanged when saving fails', async () => {
    vi.mocked(apiClient.patch).mockRejectedValueOnce(new Error('Unavailable'))
    const controller = createUserAdministrationController()
    controller.users = [{ id: 1, groups: [2] }]
    await expect(controller.updateUser(1, { groups: [] })).rejects.toThrow()
    expect(controller.getUsers[0].groups).toEqual([2])
    expect(controller.isLoading).toBe(false)
  })
})
