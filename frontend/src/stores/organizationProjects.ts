import axios from 'axios'
import type { IPanel, IProject, IResponsible } from '@/models/orgs'
import { notifySuccess } from '@/services/notify'
import { API_PATHS } from '@/stores/apiPaths'
import { runOrganizationRequest } from '@/stores/organizationRequest'
import type { OrganizationState } from '@/stores/organizationState'

/** Load registered organization projects. */
export async function fetchProjects(state: OrganizationState): Promise<void> {
  await runOrganizationRequest<IProject[]>(
    state,
    axios.get(`${API_PATHS.orgs}/projects/`),
    (data) => (state.projects = data)
  )
}

/** Create an organization project. */
export async function createProject(state: OrganizationState, data: IProject): Promise<void> {
  await runOrganizationRequest<IProject>(state, axios.post(projectsPath(), data), (created) => {
    state.projects.unshift(created)
    notifySuccess('New project added successfully.')
  })
}

/** Update an organization project. */
export async function updateProject(
  state: OrganizationState,
  id: number,
  data: IProject
): Promise<void> {
  await runOrganizationRequest<IProject>(
    state,
    axios.put(`${projectsPath()}${id}/`, data),
    (item) => {
      replaceById(state.projects, id, item)
      notifySuccess('Updated successfully.')
    }
  )
}

/** Delete an organization project. */
export async function deleteProject(state: OrganizationState, id: number): Promise<void> {
  await runOrganizationRequest<void>(state, axios.delete(`${projectsPath()}${id}/`), () => {
    state.projects = state.projects.filter((item) => item.id !== id)
    notifySuccess('Deleted successfully.')
  })
}

/** Load panels for the selected project. */
export async function fetchPanels(state: OrganizationState): Promise<void> {
  const requestedProject = state.project
  await runOrganizationRequest<IPanel[]>(
    state,
    axios.get(`${projectPath(state)}/panels/`),
    (data) => {
      if (state.project === requestedProject) state.panels = data
    }
  )
}

/** Create a project panel. */
export async function createPanel(state: OrganizationState, data: IPanel): Promise<void> {
  await runOrganizationRequest<IPanel>(
    state,
    axios.post(`${projectPath(state)}/panels/`, data),
    (created) => {
      state.panels.unshift(created)
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
    axios.put(`${projectPath(state)}/panels/${id}/`, data),
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
    axios.delete(`${projectPath(state)}/panels/${id}/`),
    () => {
      state.panels = state.panels.filter((item) => item.id !== id)
      notifySuccess('Deleted successfully.')
    }
  )
}

/** Load responsibles for one panel. */
export async function fetchResponsibles(state: OrganizationState, panel: string): Promise<void> {
  await runOrganizationRequest<IResponsible[]>(
    state,
    axios.get(`${projectPath(state)}/responsibles/`, { params: { panel } }),
    (data) => (state.responsibles = data)
  )
}

/** Create a project responsible. */
export async function createResponsible(
  state: OrganizationState,
  data: IResponsible
): Promise<void> {
  await runOrganizationRequest<IResponsible>(
    state,
    axios.post(`${projectPath(state)}/responsibles/`, data),
    (created) => {
      state.responsibles.unshift(created)
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
    axios.put(`${projectPath(state)}/responsibles/${id}/`, data),
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
    axios.delete(`${projectPath(state)}/responsibles/${id}/`),
    () => {
      state.responsibles = state.responsibles.filter((item) => item.id !== id)
      notifySuccess('Deleted successfully.')
    }
  )
}

function projectsPath(): string {
  return `${API_PATHS.orgs}/projects/`
}

function projectPath(state: OrganizationState): string {
  return `${state.project}/${API_PATHS.orgs}`
}

function replaceById<T extends { id?: number }>(items: T[], id: number, updated: T): void {
  const index = items.findIndex((item) => item.id === id)
  if (index >= 0) items[index] = { ...items[index], ...updated }
}
