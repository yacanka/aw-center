import axios from 'axios'

export interface InvitationContext {
  email: string
  expires_at: string
}

export interface CreatedInvitation extends InvitationContext {
  invitation_link: string
}

export type InvitationStatus = 'active' | 'used' | 'expired' | 'revoked'

export interface ManagedInvitation extends InvitationContext {
  id: number
  email: string
  groups: string[]
  status: InvitationStatus
  created_by: string | null
  created_at: string
  used_by: string | null
  used_at: string | null
  revoked_at: string | null
}

export interface InvitationPage {
  count: number
  next: string | null
  previous: string | null
  results: ManagedInvitation[]
}

export interface InvitationFilters {
  page: number
  page_size: number
  search?: string
  status?: InvitationStatus
}

export interface InvitationAccount {
  token: string
  username: string
  first_name: string
  last_name: string
  password: string
  password_confirm: string
}

/** Create an email-bound invitation as an authorized administrator. */
export async function createUserInvitation(
  email: string,
  groupIds: number[]
): Promise<CreatedInvitation> {
  const response = await axios.post<CreatedInvitation>('/auth/invitations/', {
    email,
    group_ids: groupIds
  })
  return response.data
}

/** List non-secret invitation lifecycle records for authorized managers. */
export async function listUserInvitations(filters: InvitationFilters): Promise<InvitationPage> {
  const response = await axios.get<InvitationPage>('/auth/invitations/', { params: filters })
  return response.data
}

/** Revoke one active invitation without changing terminal audit records. */
export async function revokeUserInvitation(invitationId: number): Promise<ManagedInvitation> {
  const response = await axios.delete<ManagedInvitation>(`/auth/invitations/${invitationId}/`)
  return response.data
}

/** Resolve a raw token without placing it in an HTTP URL. */
export async function inspectUserInvitation(token: string): Promise<InvitationContext> {
  const response = await axios.post<InvitationContext>('/auth/invitations/inspect/', { token })
  return response.data
}

/** Create an account by consuming a one-time invitation. */
export async function acceptUserInvitation(account: InvitationAccount): Promise<void> {
  await axios.post('/auth/invitations/accept/', account)
}
