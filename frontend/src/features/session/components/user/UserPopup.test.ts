// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const controller = vi.hoisted(() => ({
  getPermissions: [],
  getGroups: [],
  permissionsLoaded: true,
  groupsLoaded: true,
  updateUser: vi.fn()
}))
vi.mock('@/features/session/composables/userAdministrationController', () => ({
  useUserAdministrationController: () => controller
}))
vi.mock('@/shared/composables/forms', () => ({ validateForm: async () => true }))
import UserPopup from './UserPopup.vue'

describe('user access editor', () => {
  beforeEach(() => vi.clearAllMocks())
  it('isolates drafts and only sends editable fields', async () => {
    const wrapper = mount(UserPopup, {
      props: { canManageAccess: true },
      global: {
        stubs: {
          'n-input': true,
          'n-form-item-gi': { template: '<div><slot/></div>' },
          'n-select': true,
          'n-text': true,
          'n-tag': true,
          'n-empty': true,
          'n-grid': { template: '<div><slot/></div>' },
          'n-form': { template: '<div><slot/></div>' },
          Modal: { template: '<div><slot/><slot name="action"/></div>' },
          'n-button': { template: '<button @click="$emit(\'click\')"><slot/></button>' }
        }
      }
    })
    const original = {
      id: 8,
      first_name: 'Test',
      last_name: 'User',
      groups: [3],
      user_permissions: [4],
      is_superuser: true,
      preferences: { theme: 'dark' as const }
    }
    const vm = wrapper.vm as unknown as {
      openModal: (user: typeof original) => void
      user: typeof original
    }
    vm.openModal(original)
    await wrapper.vm.$nextTick()
    vm.user.groups.push(5)
    expect(original.groups).toEqual([3])
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() =>
      expect(controller.updateUser).toHaveBeenCalledWith(8, {
        first_name: 'Test',
        last_name: 'User',
        groups: [3, 5],
        user_permissions: [4]
      })
    )
  })
})
