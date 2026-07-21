import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import type { DataTableColumns, DataTableSortState, PaginationInfo, PopoverProps } from 'naive-ui'
import type { ICompDoc } from '@/models/compdocs'
import { useCompdocStore } from '@/stores/compdoc'
import { useOrgsStore } from '@/stores/organizations'
import { buildCompdocTableQuery } from '@/composables/compdoc/table'
import { useCompdocColumnSettings } from '@/composables/compdoc/columnSettings'

interface RemoteTableDependencies {
  project: Ref<string>
  canView: Ref<boolean>
  columnOverrides: Ref<DataTableColumns<ICompDoc>>
}

const filterIconPopover: PopoverProps = {
  trigger: 'click',
  duration: 250,
  displayDirective: 'show'
}

/** Coordinate remote pagination, filters, sorting, and server-owned columns. */
export function useCompdocRemoteTable(dependencies: RemoteTableDependencies) {
  const store = useCompdocStore()
  const orgs = useOrgsStore()
  const page = ref(1)
  const pageSize = ref(readPageSize())
  const ordering = ref<string | null>(null)
  const filters = ref<Record<string, unknown>>({})
  const columns = ref<DataTableColumns<ICompDoc>>([])
  const pagination = computed<Partial<PaginationInfo>>(() => ({
    page: page.value,
    pageSize: pageSize.value,
    itemCount: store.pagination.count,
    showSizePicker: true,
    pageSizes: [8, 25, 50, 100]
  }))
  const fetchRows = () => {
    if (!dependencies.canView.value) return Promise.resolve()
    const query = buildCompdocTableQuery(
      filters.value,
      { page: page.value, pageSize: pageSize.value },
      ordering.value
    )
    return store.fetchCompdocs(query).catch(() => undefined)
  }
  const onFilter = (key: string, value: unknown) => updateCustomFilter(key, value)
  const onClean = (key: string) => updateCustomFilter(key, null)
  const settings = useCompdocColumnSettings({
    project: dependencies.project,
    schemaVersion: computed(() => store.fieldsSchemaVersion),
    fields: computed(() => store.fields),
    columnOverrides: dependencies.columnOverrides,
    currentColumns: columns,
    ordering,
    filterValue: filters,
    optionSources: () => ({ panels: orgs.getPanelOptions, atas: orgs.getAtaOptions }),
    onFilter,
    onClean
  })

  function updateCustomFilter(key: string, value: unknown) {
    filters.value[key] = value
    page.value = 1
    void fetchRows()
  }

  async function initialize(project: string, hasViewPermission: boolean) {
    store.setProjectName(project)
    resetQueryState()
    if (!hasViewPermission) return clearTable()
    orgs.setProject(project)
    await Promise.allSettled([store.fetchCompDocFields(), orgs.fetchPanels()])
    if (store.projectName !== project) return
    if (store.fields.length) {
      settings.load()
      settings.apply()
    } else columns.value = []
    await fetchRows()
  }

  function resetQueryState() {
    page.value = 1
    ordering.value = null
    filters.value = {}
  }

  function clearTable() {
    store.clearList()
    columns.value = []
  }

  function handleFilters(updated: Record<string, unknown>) {
    store.fields
      .filter((field) => ['select', 'boolean'].includes(field.filter_kind))
      .forEach((field) => delete filters.value[field.key])
    Object.entries(updated).forEach(([key, value]) => {
      if (value !== null && value !== undefined) filters.value[key] = value
    })
    page.value = 1
    void fetchRows()
  }

  function handleSorter(sorter: DataTableSortState | DataTableSortState[] | null) {
    const selected = Array.isArray(sorter) ? sorter[0] : sorter
    ordering.value = selected?.order
      ? `${selected.order === 'descend' ? '-' : ''}${String(selected.columnKey)}`
      : null
    page.value = 1
    settings.refresh()
    void fetchRows()
  }

  function handlePage(newPage: number) {
    page.value = newPage
    void fetchRows()
  }

  function handlePageSize(newSize: number) {
    pageSize.value = Math.min(200, Math.max(1, newSize))
    page.value = 1
    localStorage.setItem('compdocs>page_size', String(pageSize.value))
    void fetchRows()
  }

  watch(
    () => [dependencies.project.value, dependencies.canView.value] as const,
    ([project, canView]) => void initialize(project, canView),
    { immediate: true }
  )
  onUnmounted(() => store.clearList())

  return {
    columns,
    pagination,
    pageSize,
    filterIconPopover,
    settings,
    initialize,
    handleFilters,
    handleSorter,
    handlePage,
    handlePageSize,
    rowKey: (row: ICompDoc) => row.id || ''
  }
}

function readPageSize() {
  const saved = Number(localStorage.getItem('compdocs>page_size')) || 8
  return Math.min(200, Math.max(1, saved))
}
