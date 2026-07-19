import { h } from 'vue'
import { NButton, type DataTableColumn } from 'naive-ui'
import type { IUser } from '@/models/auth'

/** Build the user table action column from page-owned callbacks. */
export function userActionColumn(
  updateUser: (user: IUser) => void,
  deleteUser: (user: IUser) => void
): DataTableColumn<IUser> {
  return {
    title: 'Action',
    key: 'actions',
    width: 12,
    render: (user) => [updateButton(user, updateUser), deleteButton(user, deleteUser)]
  }
}

function updateButton(user: IUser, updateUser: (user: IUser) => void) {
  return h(
    NButton,
    buttonProperties('warning', () => updateUser(user)),
    { default: () => 'Update' }
  )
}

function deleteButton(user: IUser, deleteUser: (user: IUser) => void) {
  return h(
    NButton,
    buttonProperties('error', () => deleteUser(user)),
    { default: () => 'Delete' }
  )
}

function buttonProperties(type: 'warning' | 'error', onClick: () => void) {
  return {
    ghost: true,
    size: 'small' as const,
    type,
    focusable: false,
    style: 'margin-right: 5px',
    onClick
  }
}
