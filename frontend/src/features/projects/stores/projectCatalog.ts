import { defineStore } from 'pinia'
import type {
  ProjectCapability,
  ProjectDccRole,
  ProjectManagementRole,
  ProjectRegistryItem
} from '@/features/projects/models/projectRegistry'
import {
  hasProjectDccRole,
  hasProjectManagementRole
} from '@/features/projects/models/projectRegistry'
import { fetchProjectRegistry } from '@/features/projects/api/projectRegistry'
import { formatApiError } from '@/shared/api/apiError'

export type ProjectCatalogStatus = 'unknown' | 'loading' | 'ready' | 'error'

let pendingRequest: Promise<ProjectRegistryItem[]> | null = null

/** Own the authenticated project catalog and its domain-role decisions. */
export const useProjectCatalogStore = defineStore('projectCatalog', {
  state: () => ({
    projects: [] as ProjectRegistryItem[],
    status: 'unknown' as ProjectCatalogStatus,
    error: '',
    requestVersion: 0
  }),
  getters: {
    complianceProjects: (state) =>
      state.projects.filter(
        (project) =>
          project.capabilities.includes('compliance') && project.roles.compliance !== null
      ),
    dccProjects: (state) =>
      state.projects.filter(
        (project) => project.capabilities.includes('dcc') && project.roles.dcc !== null
      ),
    hasAnyRole:
      (state) =>
      (capability: ProjectCapability): boolean =>
        state.status === 'ready' &&
        state.projects.some(
          (project) =>
            project.capabilities.includes(capability) && project.roles[capability] !== null
        ),
    roleFor: (state) => (slug: string, capability: ProjectCapability) =>
      state.projects.find((project) => project.slug === slug)?.roles[capability] || null,
    hasManagementRole:
      (state) => (slug: string, capability: ProjectCapability, minimum: ProjectManagementRole) =>
        hasProjectManagementRole(
          state.projects.find((project) => project.slug === slug)?.roles[capability],
          minimum
        ),
    hasDccRole: (state) => (slug: string, minimum: ProjectDccRole) =>
      hasProjectDccRole(state.projects.find((project) => project.slug === slug)?.roles.dcc, minimum)
  },
  actions: {
    async load(force = false): Promise<ProjectRegistryItem[]> {
      if (!force && this.status === 'ready') return this.projects
      if (pendingRequest) return pendingRequest

      const requestVersion = ++this.requestVersion
      this.status = 'loading'
      this.error = ''
      const request = fetchProjectRegistry()
      pendingRequest = request
      try {
        const projects = await request
        if (requestVersion !== this.requestVersion) return []
        this.projects = projects
        this.status = 'ready'
        return this.projects
      } catch (error) {
        if (requestVersion !== this.requestVersion) return []
        this.projects = []
        this.status = 'error'
        this.error = formatApiError(error)
        throw error
      } finally {
        if (pendingRequest === request) pendingRequest = null
      }
    },
    clear(): void {
      this.requestVersion += 1
      pendingRequest = null
      this.projects = []
      this.status = 'unknown'
      this.error = ''
    }
  }
})
