import { h, ref } from 'vue'
import { NSpin, NSpace, NTag, NText, type DataTableColumns } from 'naive-ui'
import type { ICompDoc } from '@/models/compdocs'
import { useDocproofStore } from '@/stores/docproof'

export type IssueValues = Record<string, string | null | undefined>

/** Build DocProof-aware table renderers and their shared lookup cache. */
export function useCompdocIssueColumns() {
  const proofStore = useDocproofStore()
  const issueValues = ref<IssueValues>({})
  const columns: DataTableColumns<ICompDoc> = [
    {
      key: 'cover_page_issue',
      align: 'center',
      render: (row) =>
        issueCell(row.cover_page_no, row.cover_page_issue, issueValues.value, proofStore)
    },
    {
      key: 'tech_doc_no',
      render: (row) => renderValues([row.tech_doc_no, row.tech_doc_no_2])
    },
    {
      key: 'tech_doc_issue',
      align: 'center',
      render: (row) =>
        h(NSpace, { vertical: true }, () => [
          issueCell(row.tech_doc_no, row.tech_doc_issue, issueValues.value, proofStore),
          issueCell(row.tech_doc_no_2, row.tech_doc_issue_2, issueValues.value, proofStore)
        ])
    }
  ]
  return { columns, issueValues }
}

function issueCell(
  documentNumber: unknown,
  expectedIssue: unknown,
  values: IssueValues,
  proofStore: ReturnType<typeof useDocproofStore>
) {
  const number = String(documentNumber || '')
  if (!number) return expectedIssue ? String(expectedIssue) : null
  const currentIssue = values[number]
  if (currentIssue === null) return h(NSpin, { size: 22 })
  if (currentIssue !== undefined) return issueTag(currentIssue, expectedIssue)
  return lookupTrigger(number, expectedIssue, values, proofStore)
}

function lookupTrigger(
  number: string,
  expectedIssue: unknown,
  values: IssueValues,
  proofStore: ReturnType<typeof useDocproofStore>
) {
  return h(
    NText,
    {
      title: 'Double click to check DocProof',
      class: 'cell-color',
      style: { userSelect: 'text', cursor: 'pointer' },
      onMouseenter: toggleHovered(true),
      onMouseleave: toggleHovered(false),
      onDblclick: (event: MouseEvent) => {
        event.stopPropagation()
        lookupIssue(number, values, proofStore)
      }
    },
    () => (expectedIssue ? String(expectedIssue) : '')
  )
}

function lookupIssue(
  number: string,
  values: IssueValues,
  proofStore: ReturnType<typeof useDocproofStore>
) {
  values[number] = null
  proofStore
    .search(number)
    .then((issue) => (values[number] = String(issue)))
    .catch(() => (values[number] = undefined))
}

function issueTag(currentIssue: string, expectedIssue: unknown) {
  return h(
    NTag,
    { type: currentIssue === String(expectedIssue || '') ? 'success' : 'warning', size: 'small' },
    () => currentIssue
  )
}

function renderValues(values: unknown[]) {
  return h(NSpace, {}, () =>
    values.filter(Boolean).map((value) => h(NText, {}, () => String(value)))
  )
}

function toggleHovered(hovered: boolean) {
  return (event: MouseEvent) => {
    ;(event.currentTarget as HTMLElement).classList.toggle('hovered', hovered)
  }
}
