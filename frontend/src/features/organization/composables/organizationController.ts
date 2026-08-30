import { inject, provide, reactive, type InjectionKey } from 'vue'
import type { IPerson, IPanel, IProject, IResponsible } from '@/features/organization/models/orgs'
import { toTitleCase } from '@/shared/utils/text'
import type { PaginationMeta, PaginationQuery } from '@/shared/services/pagination'
import {
  createOrganizationState,
  type OrganizationState
} from '@/features/organization/composables/organizationState'
import * as projects from '@/features/organization/api/organizationProjects'
import * as people from '@/features/organization/api/organizationPeople'
import type {
  PeopleImportResult,
  PeopleSearchPage
} from '@/features/organization/api/organizationPeople'

export interface OrganizationController extends OrganizationState {
  readonly isLoading: boolean
  readonly getProjects: IProject[]
  readonly getEnabledProjects: IProject[]
  readonly getPanels: IPanel[]
  readonly getPanelOptions: Array<{ label: string; value: string }>
  readonly getCompdocPanelOptions: Array<{ label: string; value: number }>
  readonly getAtaOptions: Array<{ label: string; value: string }>
  readonly getResponsibles: IResponsible[]
  readonly getPeople: IPerson[]
  readonly hasFetchedPeople: boolean
  readonly peoplePagination: PaginationMeta
  canManageProject(slug: string): boolean
  setProject(projectName: string): void
  fetchProjects(): Promise<void>
  fetchPanels(): Promise<void>
  createPanel(data: IPanel): Promise<void>
  updatePanel(id: number, data: IPanel): Promise<void>
  deletePanel(id: number): Promise<void>
  fetchResponsibles(panel: string): Promise<void>
  createResponsible(data: IResponsible): Promise<void>
  updateResponsible(id: number, data: IResponsible): Promise<void>
  deleteResponsible(id: number): Promise<void>
  fetchPeople(force?: boolean, query?: PaginationQuery): Promise<unknown>
  searchPeople(
    search: string,
    page?: number,
    pageSize?: number,
    signal?: AbortSignal
  ): Promise<PeopleSearchPage>
  createPerson(data: IPerson): Promise<void>
  updatePerson(id: number, data: IPerson): Promise<void>
  deletePerson(id: number): Promise<void>
  uploadPeople(file: FormData): Promise<PeopleImportResult>
}

const organizationControllerKey: InjectionKey<OrganizationController> =
  Symbol('organization-controller')

/** Create organization state scoped to one route tree. */
export function createOrganizationController(): OrganizationController {
  const state = reactive(createOrganizationState()) as OrganizationState
  const controller = state as OrganizationController

  Object.defineProperties(controller, {
    isLoading: { get: () => state.loading },
    getProjects: { get: () => state.projects },
    getEnabledProjects: { get: () => state.projects },
    getPanels: { get: () => sortedByName(state.panels) },
    getPanelOptions: { get: () => panelOptions(state.panels) },
    getCompdocPanelOptions: { get: () => compdocPanelOptions(state.panels) },
    getAtaOptions: { get: () => ataOptions(state.panels) },
    getResponsibles: { get: () => sortedByName(state.responsibles) },
    getPeople: { get: () => sortedByName(state.people) },
    hasFetchedPeople: { get: () => state.peopleFetched }
  })

  controller.canManageProject = (slug) =>
    state.projects.find((project) => project.slug === slug)?.roles.organization === 'manager'
  controller.setProject = (projectName) => {
    if (state.project === projectName) return
    state.project = projectName
    state.panels = []
    state.responsibles = []
  }
  controller.fetchProjects = () => projects.fetchProjects(state)
  controller.fetchPanels = () => projects.fetchPanels(state)
  controller.createPanel = (data) => projects.createPanel(state, data)
  controller.updatePanel = (id, data) => projects.updatePanel(state, id, data)
  controller.deletePanel = (id) => projects.deletePanel(state, id)
  controller.fetchResponsibles = (panel) => projects.fetchResponsibles(state, panel)
  controller.createResponsible = (data) => projects.createResponsible(state, data)
  controller.updateResponsible = (id, data) => projects.updateResponsible(state, id, data)
  controller.deleteResponsible = (id) => projects.deleteResponsible(state, id)
  controller.fetchPeople = (force = false, query = {}) => people.fetchPeople(state, force, query)
  controller.searchPeople = (search, page = 1, pageSize = 10, signal) =>
    people.searchPeople(state, search, page, pageSize, signal)
  controller.createPerson = (data) => people.createPerson(state, data)
  controller.updatePerson = (id, data) => people.updatePerson(state, id, data)
  controller.deletePerson = (id) => people.deletePerson(state, id)
  controller.uploadPeople = (file) => people.uploadPeople(state, file)
  return controller
}

export function provideOrganizationController(
  controller = createOrganizationController()
): OrganizationController {
  provide(organizationControllerKey, controller)
  return controller
}

export function useOrganizationController(): OrganizationController {
  const controller = inject(organizationControllerKey)
  if (!controller) throw new Error('Organization controller is outside its route boundary.')
  return controller
}

function sortedByName<T extends { name: string }>(items: T[]): T[] {
  return [...items].sort((left, right) =>
    left.name.localeCompare(right.name, 'tr', { sensitivity: 'base' })
  )
}

function panelOptions(panels: IPanel[]) {
  return [...new Set(panels.map((panel) => panel.name))]
    .sort((left, right) => left.localeCompare(right, 'tr', { sensitivity: 'base' }))
    .map((name) => ({ label: toTitleCase(name), value: name }))
}

function compdocPanelOptions(panels: IPanel[]) {
  return [...panels]
    .filter((panel): panel is IPanel & { id: number } => typeof panel.id === 'number')
    .sort((left, right) => left.name.localeCompare(right.name, 'tr', { sensitivity: 'base' }))
    .map((panel) => ({
      label: `${toTitleCase(panel.name)} · ATA ${panel.ata}`,
      value: panel.id
    }))
}

function ataOptions(panels: IPanel[]) {
  return [...panels]
    .sort((left, right) => left.ata.localeCompare(right.ata, 'tr', { sensitivity: 'base' }))
    .map((panel) => ({ label: panel.ata, value: panel.ata }))
}
