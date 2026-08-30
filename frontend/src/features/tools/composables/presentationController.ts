import type { AxiosResponse } from 'axios'
import { inject, provide, ref, type InjectionKey, type Ref } from 'vue'
import { apiClient } from '@/shared/api/http'
import type { Presentation, PresentationSlide } from '@/features/tools/models/presentation'
import { API_PATHS } from '@/shared/api/apiPaths'
import type { Job } from '@/features/jobs/api/jobs'
import { getPaginatedResults, type PaginatedResponse } from '@/shared/services/pagination'

const presentationPath = `${API_PATHS.presentations}/presentations`

export interface PresentationController {
  loading: Ref<boolean>
  presentations: Ref<Presentation[]>
  uploadPresentation(form: FormData, idempotencyKey: string): Promise<Job>
  fetchPresentations(): Promise<Presentation[]>
  removePresentation(id: string): Promise<void>
  reconvertPresentation(id: string, idempotencyKey: string): Promise<Job>
  deleteSlide(id: string): Promise<void>
  loadPresentation(id: string): Promise<Presentation>
  updateSlide(id: string, form: FormData): Promise<PresentationSlide>
}

const presentationControllerKey: InjectionKey<PresentationController> =
  Symbol('presentation-controller')

/** Create state owned by one presentation route visit. */
export function createPresentationController(): PresentationController {
  const loading = ref(false)
  const presentations = ref<Presentation[]>([])

  async function request<T>(operation: () => Promise<AxiosResponse<T>>): Promise<T> {
    loading.value = true
    try {
      return (await operation()).data
    } finally {
      loading.value = false
    }
  }

  async function uploadPresentation(form: FormData, idempotencyKey: string): Promise<Job> {
    return request(() =>
      apiClient.post<Job>(`${presentationPath}/upload/`, form, {
        headers: { 'Idempotency-Key': idempotencyKey }
      })
    )
  }

  async function fetchPresentations(): Promise<Presentation[]> {
    const payload = await request(() =>
      apiClient.get<PaginatedResponse<Presentation>>(`${presentationPath}/`, {
        params: { page_size: 100 }
      })
    )
    presentations.value = getPaginatedResults<Presentation>(payload).map(normalizePresentation)
    return presentations.value
  }

  async function removePresentation(id: string): Promise<void> {
    await request(() => apiClient.delete<void>(`${presentationPath}/${id}/`))
    presentations.value = presentations.value.filter((presentation) => presentation.id !== id)
  }

  async function reconvertPresentation(id: string, idempotencyKey: string): Promise<Job> {
    const job = await request(() =>
      apiClient.post<Job>(
        `${presentationPath}/${id}/reconvert/`,
        {},
        { headers: { 'Idempotency-Key': idempotencyKey } }
      )
    )
    const presentation = presentations.value.find((item) => item.id === id)
    if (presentation) {
      presentation.status = 'pending'
      presentation.conversion_job_id = job.id
    }
    return job
  }

  async function deleteSlide(id: string): Promise<void> {
    await request(() => apiClient.delete<void>(`${API_PATHS.presentations}/slides/${id}/`))
  }

  async function loadPresentation(id: string): Promise<Presentation> {
    return normalizePresentation(
      await request(() => apiClient.get<Presentation>(`${presentationPath}/${id}/`))
    )
  }

  async function updateSlide(id: string, form: FormData): Promise<PresentationSlide> {
    return normalizeSlide(
      await request(() =>
        apiClient.patch<PresentationSlide>(`${API_PATHS.presentations}/slides/${id}/`, form)
      )
    )
  }

  return {
    loading,
    presentations,
    uploadPresentation,
    fetchPresentations,
    removePresentation,
    reconvertPresentation,
    deleteSlide,
    loadPresentation,
    updateSlide
  }
}

export function providePresentationController(controller = createPresentationController()) {
  provide(presentationControllerKey, controller)
  return controller
}

export function usePresentationController(): PresentationController {
  const controller = inject(presentationControllerKey)
  if (!controller) throw new Error('Presentation controller is outside its route boundary.')
  return controller
}

function normalizePresentation(presentation: Presentation): Presentation {
  return {
    ...presentation,
    id: String(presentation.id),
    slides: (presentation.slides || []).map(normalizeSlide)
  }
}

function normalizeSlide(slide: PresentationSlide): PresentationSlide {
  return { ...slide, id: String(slide.id) }
}
