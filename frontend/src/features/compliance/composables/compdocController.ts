import { inject, provide, reactive, type InjectionKey } from 'vue'
import { apiClient } from '@/shared/api/http'
import type {
  ICompDoc,
  ICompDocFieldMetadata,
  IHistory
} from '@/features/compliance/models/compdocs'
import { withCompdocDisplayStatus } from '@/features/compliance/api/compdocStatus'
import {
  buildCompdocCreatePayload,
  type CompDocUpdatePayload
} from '@/features/compliance/api/compdocPayload'
import { normalizeCompdoc, normalizeCompdocFields } from '@/features/compliance/api/compdocContract'
import { handleRequest } from '@/shared/composables/promise'
import { compdocCollectionPath, compdocDocumentPath } from '@/shared/api/apiPaths'
import { notifyError, notifySuccess } from '@/shared/services/notify'
import { formatApiError } from '@/shared/api/apiError'
import {
  fetchCompdocOptions,
  isCompdocPanelReference,
  type CompdocPanelReference
} from '@/features/compliance/api/compdocOptions'
import { toTitleCase } from '@/shared/utils/text'
import {
  compactPaginationQuery,
  getPaginationMeta,
  type PaginationMeta,
  type PaginationQuery
} from '@/shared/services/pagination'

interface CompdocState {
  projectName: string
  compdocs: ICompDoc[]
  loading: boolean
  listRequestId: number
  fields: ICompDocFieldMetadata[]
  fieldsSchemaVersion: number
  fieldsError: string | null
  pagination: PaginationMeta
  panels: CompdocPanelReference[]
  lastQuery: PaginationQuery
}

export interface CompdocController extends CompdocState {
  readonly getCompdocs: ICompDoc[]
  readonly getProjectName: string
  readonly getUploadUrl: string
  readonly isLoading: boolean
  readonly getPanels: CompdocPanelReference[]
  readonly getPanelOptions: Array<{ label: string; value: number }>
  readonly getSignaturePanelOptions: Array<{ label: string; value: string }>
  readonly getAtaOptions: Array<{ label: string; value: string }>
  setProjectName(name: string): void
  clearList(): void
  checkBonusFields(): boolean
  fetchCompDocFields(): Promise<unknown>
  fetchReferencePanels(): Promise<void>
  fetchCompdocs(query?: PaginationQuery): Promise<void>
  createCompdoc(data: ICompDoc): Promise<void>
  acceptCreatedCompdoc(data: unknown): ICompDoc
  acceptUpdatedCompdoc(data: unknown): ICompDoc
  updateCompdoc(id: string, data: CompDocUpdatePayload): Promise<void>
  fetchCompdoc(id: string): Promise<ICompDoc>
  archiveCompdoc(id: string, version: number, reason: string): Promise<void>
  restoreCompdoc(id: string, version: number, reason: string): Promise<void>
  setArchiveState(id: string, version: number, reason: string, archived: boolean): Promise<void>
  fetchHistory(id: string): Promise<IHistory[]>
}

const compdocControllerKey: InjectionKey<CompdocController> = Symbol('compdoc-controller')

/** Create compliance table state scoped to one route visit. */
export function createCompdocController(): CompdocController {
  const state = reactive<CompdocState>({
    projectName: '',
    compdocs: [],
    loading: true,
    listRequestId: 0,
    fields: [],
    fieldsSchemaVersion: 0,
    fieldsError: null,
    pagination: { count: 0, next: null, previous: null },
    panels: [],
    lastQuery: {}
  })
  const controller = state as CompdocController

  Object.defineProperties(controller, {
    getCompdocs: { get: () => state.compdocs.map((row) => withCompdocDisplayStatus(row)) },
    getProjectName: { get: () => state.projectName },
    getUploadUrl: { get: () => compdocCollectionPath(state.projectName) },
    isLoading: { get: () => state.loading },
    getPanels: { get: () => [...state.panels] },
    getPanelOptions: { get: () => panelOptions(state.panels) },
    getSignaturePanelOptions: { get: () => signaturePanelOptions(state.panels) },
    getAtaOptions: { get: () => ataOptions(state.panels) }
  })

  controller.setProjectName = (name) => {
    if (state.projectName === name) return
    state.projectName = name
    state.panels = []
    state.lastQuery = {}
  }
  controller.clearList = () => {
    state.listRequestId += 1
    state.compdocs = []
    state.loading = false
  }
  controller.checkBonusFields = () => state.fields.some((field) => field.key === 'tech_doc_no_2')
  controller.fetchCompDocFields = () => fetchCompDocFields(state)
  controller.fetchReferencePanels = () => fetchReferencePanels(state)
  controller.fetchCompdocs = (query) => fetchCompdocs(state, query)
  controller.createCompdoc = (data) => createCompdoc(state, data)
  controller.acceptCreatedCompdoc = (data) => {
    const created = normalizeCompdoc(data)
    state.compdocs.unshift(created)
    return created
  }
  controller.acceptUpdatedCompdoc = (data) => {
    const updated = normalizeCompdoc(data)
    const index = state.compdocs.findIndex((document) => document.id === updated.id)
    if (index >= 0) state.compdocs[index] = updated
    return updated
  }
  controller.updateCompdoc = (id, data) => updateCompdoc(state, id, data)
  controller.fetchCompdoc = (id) => fetchCompdoc(state, id)
  controller.archiveCompdoc = (id, version, reason) =>
    setArchiveState(state, id, version, reason, true)
  controller.restoreCompdoc = (id, version, reason) =>
    setArchiveState(state, id, version, reason, false)
  controller.setArchiveState = (id, version, reason, archived) =>
    setArchiveState(state, id, version, reason, archived)
  controller.fetchHistory = (id) => fetchHistory(state, id)
  return controller
}

export function provideCompdocController(
  controller = createCompdocController()
): CompdocController {
  provide(compdocControllerKey, controller)
  return controller
}

export function useCompdocController(): CompdocController {
  const controller = inject(compdocControllerKey)
  if (!controller) throw new Error('CompDoc controller is outside its route boundary.')
  return controller
}

async function fetchCompDocFields(state: CompdocState): Promise<unknown> {
  const requestedProject = state.projectName
  state.fieldsError = null
  try {
    return await handleRequest<unknown>(
      apiClient.get(`${compdocCollectionPath(state.projectName)}fields/`),
      (data) => {
        if (state.projectName !== requestedProject) return
        const fields = normalizeCompdocFields(data)
        state.fields = fields.fields
        state.fieldsSchemaVersion = fields.schema_version
      },
      (message) => {
        if (state.projectName !== requestedProject) return
        state.fields = []
        state.fieldsError = message
        notifyError(message)
      }
    )
  } catch {
    return null
  }
}

async function fetchCompdocs(state: CompdocState, query?: PaginationQuery): Promise<void> {
  const requestedProject = state.projectName
  if (query) state.lastQuery = { ...query }
  const requestedQuery = query || state.lastQuery
  const requestId = ++state.listRequestId
  const isCurrent = () =>
    state.projectName === requestedProject && state.listRequestId === requestId
  state.loading = true
  const response = await handleRequest<unknown[]>(
    apiClient.get(compdocCollectionPath(state.projectName), {
      params: compactPaginationQuery(requestedQuery),
      paramsSerializer: { indexes: null }
    }),
    (data) => {
      if (isCurrent()) state.compdocs = data.map(normalizeCompdoc)
    },
    (message) => {
      if (isCurrent()) notifyError(message)
    },
    () => {
      if (isCurrent()) state.loading = false
    }
  )
  if (isCurrent()) state.pagination = getPaginationMeta<ICompDoc>(response) || state.pagination
}

async function fetchReferencePanels(state: CompdocState): Promise<void> {
  const requestedProject = state.projectName
  try {
    const options = await fetchCompdocOptions(requestedProject, 'panel')
    if (state.projectName !== requestedProject) return
    state.panels = options.filter(isCompdocPanelReference)
  } catch (error) {
    if (state.projectName !== requestedProject) return
    state.panels = []
    notifyError(formatApiError(error))
  }
}

async function createCompdoc(state: CompdocState, data: ICompDoc): Promise<void> {
  state.loading = true
  await handleRequest<unknown>(
    apiClient.post(compdocCollectionPath(state.projectName), buildCompdocCreatePayload(data)),
    (payload) => {
      state.compdocs.unshift(normalizeCompdoc(payload))
      notifySuccess('New document added successfully.')
    },
    notifyError,
    () => (state.loading = false)
  )
}

async function updateCompdoc(
  state: CompdocState,
  id: string,
  data: CompDocUpdatePayload
): Promise<void> {
  state.loading = true
  await handleRequest<unknown>(
    apiClient.put(`${compdocDocumentPath(state.projectName, id)}/`, data),
    (payload) => {
      const updated = normalizeCompdoc(payload)
      const index = state.compdocs.findIndex((document) => document.id === id)
      if (index >= 0) state.compdocs[index] = updated
      notifySuccess('Updated successfully.')
    },
    notifyError,
    () => (state.loading = false)
  )
}

async function fetchCompdoc(state: CompdocState, id: string): Promise<ICompDoc> {
  const response = await apiClient.get<unknown>(`${compdocDocumentPath(state.projectName, id)}/`)
  const document = normalizeCompdoc(response.data)
  const index = state.compdocs.findIndex((item) => item.id === id)
  if (index >= 0) state.compdocs[index] = document
  return document
}

async function setArchiveState(
  state: CompdocState,
  id: string,
  version: number,
  reason: string,
  archived: boolean
): Promise<void> {
  state.loading = true
  await handleRequest<{ id: string; version: number }>(
    apiClient.post(
      `${compdocDocumentPath(state.projectName, id)}/${archived ? 'archive' : 'restore'}/`,
      { version, reason }
    ),
    () => {
      state.compdocs = state.compdocs.filter((document) => document.id !== id)
      notifySuccess(archived ? 'Document archived successfully.' : 'Document restored.')
    },
    notifyError,
    () => (state.loading = false)
  )
}

async function fetchHistory(state: CompdocState, id: string): Promise<IHistory[]> {
  state.loading = true
  let history: IHistory[] = []
  await handleRequest<IHistory[]>(
    apiClient.get(`${compdocDocumentPath(state.projectName, id)}/history/`),
    (data) => (history = data),
    notifyError,
    () => (state.loading = false)
  )
  return history
}

function panelOptions(panels: CompdocPanelReference[]) {
  return [...panels]
    .sort((left, right) => left.name.localeCompare(right.name, 'tr', { sensitivity: 'base' }))
    .map((panel) => ({
      label: `${toTitleCase(panel.name)} · ATA ${panel.ata}`,
      value: panel.id
    }))
}

function signaturePanelOptions(panels: CompdocPanelReference[]) {
  return [...new Set(panels.map((panel) => panel.name))]
    .sort((left, right) => left.localeCompare(right, 'tr', { sensitivity: 'base' }))
    .map((name) => ({ label: toTitleCase(name), value: name }))
}

function ataOptions(panels: CompdocPanelReference[]) {
  return [...new Set(panels.map((panel) => panel.ata))]
    .sort((left, right) => left.localeCompare(right, 'tr', { sensitivity: 'base' }))
    .map((ata) => ({ label: ata, value: ata }))
}
