import { apiClient as axios } from '@/shared/api/http'
import type { AxiosResponse } from 'axios'
import type { IPanel, IProject, IResponsible } from '@/features/organization/models/orgs'
import { notifyError, notifySuccess } from '@/shared/services/notify'
import { getPaginatedResults } from '@/shared/services/pagination'
import { organizationPath } from '@/shared/api/apiPaths'
import { runOrganizationRequest } from '@/features/organization/api/organizationRequest'
import type { OrganizationState } from '@/features/organization/composables/organizationState'
import { useProjectCatalogStore } from '@/features/projects/stores/projectCatalog'

/** Load registered organization projects. */
export async function fetchProjects(state: OrganizationState): Promise<void> {
  state.loading = true
  try {
    const catalog = useProjectCatalogStore()
    await catalog.load()
    state.projects = catalog.projects.filter(
      (project) =>
        project.capabilities.includes('organization') && project.roles.organization !== null
    ) as IProject[]
  } catch (error) {
    state.projects = []
    notifyError(error instanceof Error ? error.message : 'Project catalog is unavailable.')
    throw error
  } finally {
    state.loading = false
  }
}

/** Load panels for the selected project. */
export async function fetchPanels(state: OrganizationState): Promise<void> {
  if (!state.project) {
    state.panels = []
    return
  }
  const requestedProject = state.project
  await runOrganizationRequest<IPanel[]>(
    state,
    fetchAllPanels(organizationPath(state.project, 'panels')),
    (panels) => {
      if (state.project === requestedProject) {
        state.panels = panels.map((panel) => ({
          ...panel,
          project: panel.project_slug || requestedProject
        }))
      }
    }
  )
}

async function fetchAllPanels(path: string): Promise<AxiosResponse<IPanel[]>> {
  const panels: IPanel[] = []
  let next: string | null = path
  let params: { page_size: number } | undefined = { page_size: 200 }
  let firstResponse: AxiosResponse<unknown> | undefined
  while (next) {
    const response: AxiosResponse<unknown> = await axios.get(next, { params })
    firstResponse ??= response
    const page = getPaginatedResults<IPanel>(response.data)
    panels.push(...page)
    next = isPaginatedPanelResponse(response.data) ? response.data.next : null
    params = undefined
  }
  if (!firstResponse) throw new Error('Panel collection URL is missing.')
  return { ...firstResponse, data: panels }
}

function isPaginatedPanelResponse(value: unknown): value is { next: string | null } {
  return Boolean(value && typeof value === 'object' && 'next' in value)
}

/** Create a project panel. */
export async function createPanel(state: OrganizationState, data: IPanel): Promise<void> {
  await runOrganizationRequest<IPanel>(
    state,
    axios.post(organizationPath(state.project, 'panels'), panelPayload(data)),
    (created) => {
      state.panels.unshift({ ...created, project: state.project })
      notifySuccess('New panel added successfully.')
    }
  )
}

/** Update a project panel. */
export async function updatePanel(
  state: OrganizationState,
  id: number,
  data: IPanel
): Promise<void> {
  await runOrganizationRequest<IPanel>(
    state,
    axios.put(organizationPath(state.project, 'panels', id), panelPayload(data)),
    (item) => {
      replaceById(state.panels, id, item)
      notifySuccess('Updated successfully.')
    }
  )
}

/** Delete a project panel. */
export async function deletePanel(state: OrganizationState, id: number): Promise<void> {
  await runOrganizationRequest<void>(
    state,
    axios.delete(organizationPath(state.project, 'panels', id)),
    () => {
      state.panels = state.panels.filter((item) => item.id !== id)
      notifySuccess('Deleted successfully.')
    }
  )
}

/** Load responsibles for one panel. */
export async function fetchResponsibles(state: OrganizationState, panel: string): Promise<void> {
  if (!state.project) {
    state.responsibles = []
    return
  }
  const requestedProject = state.project
  const requestId = ++state.responsiblesRequestId
  await runOrganizationRequest<unknown>(
    state,
    axios.get(organizationPath(state.project, 'responsible-assignments'), {
      params: { panel, page_size: 200 }
    }),
    (data) => {
      if (state.project === requestedProject && state.responsiblesRequestId === requestId) {
        state.responsibles = getPaginatedResults<IResponsible>(data)
      }
    }
  )
}

/** Create a project responsible. */
export async function createResponsible(
  state: OrganizationState,
  data: IResponsible
): Promise<void> {
  await runOrganizationRequest<IResponsible>(
    state,
    axios.post(
      organizationPath(state.project, 'responsible-assignments'),
      responsiblePayload(data)
    ),
    (created) => {
      state.responsibles.unshift({ ...created, project: state.project })
      notifySuccess('New person added successfully.')
    }
  )
}

/** Update a project responsible. */
export async function updateResponsible(
  state: OrganizationState,
  id: number,
  data: IResponsible
): Promise<void> {
  await runOrganizationRequest<IResponsible>(
    state,
    axios.put(
      organizationPath(state.project, 'responsible-assignments', id),
      responsiblePayload(data)
    ),
    (item) => {
      replaceById(state.responsibles, id, item)
      notifySuccess('Updated successfully.')
    }
  )
}

/** Delete a project responsible without mutating the people directory. */
export async function deleteResponsible(state: OrganizationState, id: number): Promise<void> {
  await runOrganizationRequest<void>(
    state,
    axios.delete(organizationPath(state.project, 'responsible-assignments', id)),
    () => {
      state.responsibles = state.responsibles.filter((item) => item.id !== id)
      notifySuccess('Deleted successfully.')
    }
  )
}

function replaceById<T extends { id?: number }>(items: T[], id: number, updated: T): void {
  const index = items.findIndex((item) => item.id === id)
  if (index >= 0) items[index] = { ...items[index], ...updated }
}

function panelPayload(panel: IPanel) {
  return { name: panel.name, discipline: panel.discipline || '', ata: panel.ata }
}

function responsiblePayload(responsible: IResponsible) {
  return {
    panel: responsible.panel,
    person_id: responsible.person_id,
    responsibility_role: responsible.responsibility_role
  }
}
