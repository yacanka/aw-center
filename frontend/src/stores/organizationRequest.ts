import type { AxiosResponse } from 'axios'
import { handleRequest } from '@/composables/promise'
import { notifyError } from '@/services/notify'
import type { OrganizationState } from '@/stores/organizationState'

/** Run an organization request with shared loading and actionable error behavior. */
export async function runOrganizationRequest<T>(
  state: OrganizationState,
  request: Promise<AxiosResponse<T>>,
  onSuccess: (data: T) => void
): Promise<T> {
  state.loading = true
  return handleRequest<T>(request, onSuccess, notifyError, () => (state.loading = false))
}
