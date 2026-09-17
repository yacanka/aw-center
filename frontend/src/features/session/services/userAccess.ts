import type { IPermission, IUser } from '@/features/session/models/auth'

export function permissionKey(permission: IPermission): string {
  return `${permission.content_type?.app_label}.${permission.codename}`
}

export function effectivePermissions(user: IUser): IPermission[] {
  const permissions = [
    ...(user.permissions || []),
    ...(user.group_details || []).flatMap((group) => group.permissions || [])
  ]
  return [
    ...new Map(permissions.map((permission) => [permissionKey(permission), permission])).values()
  ].sort((a, b) => permissionKey(a).localeCompare(permissionKey(b)))
}

export function permissionDescription(permission: IPermission): string {
  const descriptions: Record<string, string> = {
    'auth.view_user': 'View all users and their assigned roles and permissions.',
    'auth.add_user': 'Create user accounts. Creating invitations also requires staff status.',
    'auth.change_user': 'Edit users and assign or remove their roles and direct permissions.',
    'auth.delete_user': 'Delete user accounts.',
    'auth.view_group': 'View roles and the permissions included in each role.',
    'auth.add_group': 'Create roles.',
    'auth.change_group': 'Change roles and their permissions, affecting every member.',
    'auth.delete_group': 'Delete roles and remove the access they grant to members.'
  }
  return (
    descriptions[permissionKey(permission)] ||
    `${permission.name || permission.codename}. Applies where ${permission.content_type?.app_label || 'the application'} checks this permission; project and record access rules still apply.`
  )
}
