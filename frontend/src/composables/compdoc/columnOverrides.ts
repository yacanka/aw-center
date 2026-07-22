import { h, ref } from 'vue'
import { NTag, type DataTableColumns } from 'naive-ui'
import type { ICompDoc } from '@/models/compdocs'
import { statusColors } from '@/services/compdocCatalog'
import { humanizeCompdocStatus } from '@/services/compdocWorkspace'
import { useCompdocIssueColumns } from '@/composables/compdoc/issueColumns'

/** Return renderer-only overrides layered onto the server field schema. */
export function useCompdocColumnOverrides() {
  const issueColumns = useCompdocIssueColumns()
  const columns = ref<DataTableColumns<ICompDoc>>([
    ...issueColumns.columns,
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
