import { defineStore } from 'pinia'
import type { IPerson, IPanel, IResponsible } from '@/models/orgs'
import { toTitleCase } from '@/utils/text'
import type { PaginationQuery } from '@/services/pagination'
import { createOrganizationState } from '@/stores/organizationState'
import * as projects from '@/stores/organizationProjects'
import * as people from '@/stores/organizationPeople'
import type { PeopleImportResult } from '@/stores/organizationPeople'

export const useOrgsStore = defineStore('orgs', {
  state: createOrganizationState,
  getters: {
    isLoading: (state) => state.loading,
    getProjects: (state) => state.projects,
    getEnabledProjects: (state) => state.projects.filter((project) => project.enabled),
    getPanels: (state) => sortedByName(state.panels),
    getPanelOptions: (state) => panelOptions(state.panels),
    getAtaOptions: (state) => ataOptions(state.panels),
    getResponsibles: (state) => sortedByName(state.responsibles),
    getPeople: (state) => sortedByName(state.people),
    hasFetchedPeople: (state) => state.peopleFetched
  },
  actions: {
    /** Select the project used by panel and responsible operations. */
    setProject(projectName: string): void {
      if (this.project === projectName) return
      this.project = projectName
      this.panels = []
      this.responsibles = []
    },
    /** Load organization projects. */
    fetchProjects(): Promise<void> {
      return projects.fetchProjects(this)
    },
    /** Load panels for the selected project. */
    fetchPanels(): Promise<void> {
      return projects.fetchPanels(this)
    },
    /** Create a project panel. */
    createPanel(data: IPanel): Promise<void> {
      return projects.createPanel(this, data)
    },
    /** Update a project panel. */
    updatePanel(id: number, data: IPanel): Promise<void> {
      return projects.updatePanel(this, id, data)
    },
    /** Delete a project panel. */
    deletePanel(id: number): Promise<void> {
      return projects.deletePanel(this, id)
    },
    /** Load panel responsibles. */
    fetchResponsibles(panel: string): Promise<void> {
      return projects.fetchResponsibles(this, panel)
    },
    /** Create a panel responsible. */
    createResponsible(data: IResponsible): Promise<void> {
      return projects.createResponsible(this, data)
    },
    /** Update a panel responsible. */
    updateResponsible(id: number, data: IResponsible): Promise<void> {
      return projects.updateResponsible(this, id, data)
    },
    /** Delete a panel responsible. */
    deleteResponsible(id: number): Promise<void> {
      return projects.deleteResponsible(this, id)
    },
    /** Load or reuse the people directory page. */
    fetchPeople(force = false, query: PaginationQuery = {}): Promise<unknown> {
      return people.fetchPeople(this, force, query)
    },
    /** Search the people directory. */
    searchPeople(
      search: string,
      page = 1,
      pageSize = 10,
      signal?: AbortSignal
    ): Promise<people.PeopleSearchPage> {
      return people.searchPeople(search, page, pageSize, signal)
    },
    /** Create a directory person. */
    createPerson(data: IPerson): Promise<void> {
      return people.createPerson(this, data)
    },
    /** Update a directory person. */
    updatePerson(id: number, data: IPerson): Promise<void> {
      return people.updatePerson(this, id, data)
    },
    /** Delete a directory person. */
    deletePerson(id: number): Promise<void> {
      return people.deletePerson(this, id)
    },
    /** Import people from a validated workbook. */
    uploadPeople(file: FormData): Promise<PeopleImportResult> {
      return people.uploadPeople(this, file)
    }
  }
})

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

function ataOptions(panels: IPanel[]) {
  return [...panels]
    .sort((left, right) => left.ata.localeCompare(right.ata, 'tr', { sensitivity: 'base' }))
    .map((panel) => ({ label: panel.ata, value: panel.ata }))
}
