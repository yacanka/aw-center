import type { AxiosResponse } from 'axios'
import { handleRequest } from '@/shared/composables/promise'
import { notifyError } from '@/shared/services/notify'
import type { OrganizationState } from '@/features/organization/composables/organizationState'

/** Run an organization request with shared loading and actionable error behavior. */
export async function runOrganizationRequest<T>(
  state: OrganizationState,
  request: Promise<AxiosResponse<T>>,
  onSuccess: (data: T) => void
): Promise<T> {
  state.loading = true
  return handleRequest<T>(request, onSuccess, notifyError, () => (state.loading = false))
}
