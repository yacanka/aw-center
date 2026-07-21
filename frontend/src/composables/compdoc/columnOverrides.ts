import { h, ref, type Ref } from 'vue'
import { NButton, NSpace, NTag, type DataTableColumns } from 'naive-ui'
import { Delete24Regular, Document24Regular, Eye24Regular } from '@vicons/fluent'
import Details from '@/components/compdoc/DetailedInfo.vue'
import type { ICompDoc } from '@/models/compdocs'
import { statusColors } from '@/services/compdocCatalog'
import { useCompdocStore } from '@/stores/compdoc'
import { useCompdocIssueColumns } from '@/composables/compdoc/issueColumns'

interface OverrideDependencies {
  canDelete: Ref<boolean>
  popup: Ref<any>
  download: Ref<any>
}

/** Return renderer-only overrides layered onto the server field schema. */
export function useCompdocColumnOverrides(dependencies: OverrideDependencies) {
  const store = useCompdocStore()
  const issueColumns = useCompdocIssueColumns()
  const columns = ref<DataTableColumns<ICompDoc>>([
    {
      type: 'expand',
      width: 48,
      expandable: () => true,
      renderExpand: (row) => h(Details, { compdoc: row })
    },
    ...issueColumns.columns,
    { key: 'status', render: renderStatus },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (row) => renderActions(row, dependencies, store)
    }
  ])
  return { columns, issueValues: issueColumns.issueValues }
}

function renderStatus(row: ICompDoc) {
  const status = String(row.status || 'unknown')
  const colors = statusColors[status]
  return h(
    NTag,
    {
      color: colors ? { color: colors.color25, textColor: colors.color } : undefined,
      bordered: false
    },
    () => humanizeStatus(status)
  )
}

function renderActions(
  row: ICompDoc,
  dependencies: OverrideDependencies,
  store: ReturnType<typeof useCompdocStore>
) {
  return h(NSpace, {}, () => [
    actionButton('info', Eye24Regular, () => dependencies.popup.value.openModal(row, 'view')),
    actionButton('warning', Document24Regular, () =>
      dependencies.download.value.openModal('Cover Page')
    ),
    dependencies.canDelete.value
      ? actionButton('error', Delete24Regular, () => confirmDeletion(row, store))
      : null
  ])
}

function actionButton(type: 'info' | 'warning' | 'error', icon: object, onClick: () => void) {
  return h(NButton, {
    ghost: true,
    size: 'small',
    type,
    focusable: false,
    renderIcon: () => h(icon),
    onClick
  })
}

function confirmDeletion(row: ICompDoc, store: ReturnType<typeof useCompdocStore>) {
  window.$dialog.error({
    title: 'Delete',
    content: 'Are you sure to delete?',
    positiveText: 'Yes',
    negativeText: 'No',
    onPositiveClick: () => row.id && store.deleteCompdoc(row.id)
  })
}

function humanizeStatus(status: string) {
  const words = status.replaceAll('_', ' ').replaceAll('-', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}
