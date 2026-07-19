import axios, { type AxiosResponse } from 'axios'
import { defineStore } from 'pinia'
import { handleRequest } from '@/composables/promise'
import type { Presentation, PresentationMutationResult } from '@/models/presentation'
import { notifyError, notifySuccess } from '@/services/notify'
import { API_PATHS } from '@/stores/apiPaths'

const presentationPath = `${API_PATHS.presentations}/presentations`

export const usePptxStore = defineStore('pptxgallery', {
  state: () => ({ loading: false, presentations: [] as Presentation[] }),
  getters: {
    isLoading: (state) => state.loading,
    getPresentations: (state) => state.presentations
  },
  actions: {
    /** Upload and convert a validated PowerPoint presentation. */
    async uploadPresentation(form: FormData): Promise<Presentation> {
      this.loading = true
      return handleRequest<Presentation>(
        axios.post(`${presentationPath}/upload/`, form),
        () => notifySuccess('Presentation content successfully uploaded.'),
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Refresh the presentation gallery. */
    async fetchPresentations(): Promise<Presentation[]> {
      this.loading = true
      return handleRequest<Presentation[]>(
        axios.get(`${presentationPath}/`),
        (data) => (this.presentations = data),
        notifyError,
        () => (this.loading = false)
      )
    },
    /** Remove a presentation and its generated slides. */
    async removePresentation(id: number): Promise<PresentationMutationResult> {
      return this.mutate(() =>
        axios.delete<PresentationMutationResult>(`${presentationPath}/${id}/`)
      )
    },
    /** Re-run conversion for an existing presentation. */
    async reconvertPresentation(id: number): Promise<PresentationMutationResult> {
      return this.mutate(() =>
        axios.post<PresentationMutationResult>(`${presentationPath}/${id}/reconvert/`)
      )
    },
    /** Delete one generated slide. */
    async deleteSlide(id: number): Promise<PresentationMutationResult> {
      return this.mutate(() =>
        axios.delete<PresentationMutationResult>(`${API_PATHS.presentations}/slides/${id}/`)
      )
    },
    /** Load a presentation with its generated slide records. */
    async loadSlide(id: number): Promise<Presentation> {
      return this.mutate(() => axios.get<Presentation>(`${presentationPath}/${id}/`))
    },
    /** Replace a generated slide image. */
    async updateSlide(id: number, form: FormData): Promise<PresentationMutationResult> {
      return this.mutate(() =>
        axios.patch<PresentationMutationResult>(`${API_PATHS.presentations}/slides/${id}/`, form)
      )
    },
    async mutate<T>(request: () => Promise<AxiosResponse<T>>): Promise<T> {
      this.loading = true
      return handleRequest<T>(
        request(),
        () => undefined,
        notifyError,
        () => (this.loading = false)
      )
    }
  }
})
