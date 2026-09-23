import type { IGroup, IPermission, IUser } from '@/features/session/models/auth'

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
    'auth.view_user': 'View users, roles and permissions. Requires administrator status.',
    'auth.add_user': 'Create user accounts. Creating invitations also requires staff status.',
    'auth.change_user':
      'Edit ordinary user profiles. Only superusers can change account access, roles or direct permissions.',
    'auth.delete_user': 'Delete user accounts.',
    'auth.view_group': 'View shared roles and their permissions. Requires administrator status.',
    'auth.add_group': 'Create shared roles (superusers only).',
    'auth.change_group': 'Change shared roles for every member (superusers only).',
    'auth.delete_group': 'Remove a shared role and its inherited access (superusers only).'
  }
  return (
    descriptions[permissionKey(permission)] ||
    `${permission.name || permission.codename}. Applies where ${permission.content_type?.app_label || 'the application'} checks this permission; project and record access rules still apply.`
  )
}

export function isCriticalRole(group: IGroup): boolean {
  return (group.permissions || []).some(
    (permission) =>
      permission.content_type?.app_label === 'auth' || permission.codename?.startsWith('delete_')
  )
}

export function roleDescription(group: IGroup): string {
  const permissions = group.permissions || []
  const critical = permissions.filter(
    (permission) =>
      permission.content_type?.app_label === 'auth' || permission.codename?.startsWith('delete_')
  )
  if (critical.length)
    return `Sensitive access: ${critical
      .slice(0, 3)
      .map((permission) => permission.name || permission.codename)
      .join(
        ', '
      )}${critical.length > 3 ? ' and more' : ''}. Administrative actions also require staff status; access changes require a superuser.`
  if (!permissions.length)
    return 'No system permissions assigned. Project roles are listed separately for each user.'
  return `${permissions.length} permissions: ${permissions
    .slice(0, 3)
    .map((permission) => permission.name || permission.codename)
    .join(', ')}${permissions.length > 3 ? ' and more' : ''}. Project access rules still apply.`
}
