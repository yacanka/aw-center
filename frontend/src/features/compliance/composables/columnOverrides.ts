import { h, ref } from 'vue'
import { NTag, type DataTableColumns } from 'naive-ui'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { statusColors } from '@/features/compliance/api/compdocCatalog'
import { humanizeCompdocStatus } from '@/features/compliance/api/compdocWorkspace'
import { useCompdocIssueColumns } from '@/features/compliance/composables/issueColumns'
import type { OrganizationController } from '@/features/organization/composables/organizationController'

/** Return renderer-only overrides layered onto the server field schema. */
export function useCompdocColumnOverrides(orgs: OrganizationController) {
  const issueColumns = useCompdocIssueColumns()
  const columns = ref<DataTableColumns<ICompDoc>>([
    ...issueColumns.columns,
    {
      key: 'panel',
      render: (row) =>
        row.panel_name || orgs.getPanels.find((panel) => panel.id === row.panel)?.name || '—'
    },
    { key: 'status', render: renderStatus }
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
    () => humanizeCompdocStatus(status)
  )
}
