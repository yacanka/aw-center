import { formatTurkishDate, formatTurkishDateTime } from '@/shared/utils/time'
import { h, ref } from 'vue'
import { NTag, type DataTableColumns } from 'naive-ui'
import type { ICompDoc } from '@/features/compliance/models/compdocs'
import { statusColors } from '@/features/compliance/api/compdocCatalog'
import { humanizeCompdocStatus } from '@/features/compliance/api/compdocWorkspace'
import { useCompdocIssueColumns } from '@/features/compliance/composables/issueColumns'
import type { CompdocController } from '@/features/compliance/composables/compdocController'

/** Return renderer-only overrides layered onto the server field schema. */
export function useCompdocColumnOverrides(store: CompdocController) {
  const issueColumns = useCompdocIssueColumns()
  const columns = ref<DataTableColumns<ICompDoc>>([
    ...issueColumns.columns,
    ...(
      ['target_date', 'revised_target_date', 'release_date', 'next_action_due_date'] as const
    ).map((key) => ({
      key,
      render: (row: ICompDoc) => (row[key] ? formatTurkishDate(row[key]) : '—')
    })),
    ...(['created_at', 'updated_at'] as const).map((key) => ({
      key,
      render: (row: ICompDoc) => (row[key] ? formatTurkishDateTime(row[key]) : '—')
    })),
    {
      key: 'panel',
      render: (row) =>
        row.panel_name || store.getPanels.find((panel) => panel.id === row.panel)?.name || '—'
    },
    { key: 'status', render: renderStatus }
  ])
  return { columns, issueValues: issueColumns.issueValues }
}

function renderStatus(row: ICompDoc) {
  const status = String(row.status || 'unknown')
  const colors =
    statusColors[row.status_label === 'In Design (date missing)' ? 'missing_target' : status]
  return h(
    NTag,
    {
      color: colors ? { color: colors.color25, textColor: colors.color } : undefined,
      bordered: false
    },
    () => row.status_label || humanizeCompdocStatus(status)
  )
}
