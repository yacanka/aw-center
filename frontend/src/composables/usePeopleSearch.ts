import { computed, onBeforeUnmount, ref } from 'vue'
import type { IPerson } from '@/models/orgs'
import { useOrgsStore } from '@/stores/organizations'
import type { PeopleSearchPage } from '@/stores/organizationPeople'

export type PeopleSearchState =
  'idle' | 'short' | 'loading' | 'loading-more' | 'ready' | 'empty' | 'error'

/** Manage bounded, cancellable and server-paginated people lookup state. */
export function usePeopleSearch(onSearch: (query: string) => void) {
  const controller = new PeopleSearchController(onSearch)
  onBeforeUnmount(() => controller.cancel())
  return {
    people: controller.people,
    state: controller.state,
    total: controller.total,
    hasMore: controller.hasMore,
    schedule: (value: string, delay?: number) => controller.schedule(value, delay),
    loadMore: () => controller.loadMore(),
    retry: () => controller.retry(),
    cancel: () => controller.cancel()
  }
}

class PeopleSearchController {
  readonly people = ref<IPerson[]>([])
  readonly state = ref<PeopleSearchState>('idle')
  readonly total = ref(0)
  readonly hasMore = computed(() => this.people.value.length < this.total.value)
  private readonly store = useOrgsStore()
  private page = 0
  private query = ''
  private timer: ReturnType<typeof setTimeout> | null = null
  private requestController: AbortController | null = null
  private requestId = 0

  constructor(private readonly onSearch: (query: string) => void) {}

  schedule(value: string, delay = 300): void {
    this.cancel()
    this.resetResults()
    this.query = value.trim()
    if (!this.query) return this.updateShortQuery('idle')
    if (this.query.length < 2) return this.updateShortQuery('short')
    this.state.value = 'loading'
    this.timer = setTimeout(() => void this.searchPage(1, false), delay)
  }

  loadMore(): void {
    if (!this.hasMore.value || this.state.value == 'loading-more') return
    void this.searchPage(this.page + 1, true)
  }

  retry(): void {
    if (this.query.length >= 2) void this.searchPage(1, false)
  }

  cancel(): void {
    this.requestId += 1
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    this.requestController?.abort()
    this.requestController = null
  }

  private async searchPage(targetPage: number, append: boolean): Promise<void> {
    const context = this.createRequestContext()
    this.state.value = append ? 'loading-more' : 'loading'
    if (!append) this.onSearch(this.query)
    try {
      const result = await this.fetchPage(targetPage, context.controller)
      if (context.id == this.requestId) this.applyPage(result, append)
    } catch {
      if (context.id == this.requestId) this.state.value = 'error'
    } finally {
      if (this.requestController == context.controller) this.requestController = null
    }
  }

  private fetchPage(page: number, controller: AbortController): Promise<PeopleSearchPage> {
    return this.store.searchPeople(this.query, page, 10, controller.signal)
  }

  private applyPage(result: PeopleSearchPage, append: boolean): void {
    const people = append ? [...this.people.value, ...result.results] : result.results
    this.people.value = uniquePeople(people)
    this.total.value = result.count
    this.page = result.page
    this.state.value = this.people.value.length ? 'ready' : 'empty'
  }

  private createRequestContext(): { id: number; controller: AbortController } {
    this.requestController?.abort()
    this.requestController = new AbortController()
    return { id: ++this.requestId, controller: this.requestController }
  }

  private resetResults(): void {
    this.people.value = []
    this.total.value = 0
    this.page = 0
  }

  private updateShortQuery(nextState: PeopleSearchState): void {
    this.state.value = nextState
    this.onSearch('')
  }
}

function uniquePeople(people: IPerson[]): IPerson[] {
  const unique = new Map(people.map((person) => [person.id ?? person.person_id, person]))
  return [...unique.values()]
}
