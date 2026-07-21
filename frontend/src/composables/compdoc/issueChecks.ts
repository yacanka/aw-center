import { ref, type Ref } from 'vue'
import type { ICompDoc } from '@/models/compdocs'
import { useDocproofStore } from '@/stores/docproof'
import type { IssueValues } from '@/composables/compdoc/issueColumns'
import {
  collectUniqueTechDocumentNumbers,
  mapWithConcurrencyLimit,
  waitForRetry
} from '@/composables/compdoc/table'

const CONCURRENCY_LIMIT = 4
const RETRY_LIMIT = 1
const RETRY_DELAY_MILLISECONDS = 600

/** Manage bounded, retryable DocProof issue checks for visible documents. */
export function useCompdocIssueChecks(rows: Ref<ICompDoc[]>, issueValues: Ref<IssueValues>) {
  const proofStore = useDocproofStore()
  const checking = ref(false)
  const progress = ref({ completed: 0, total: 0 })

  async function checkAll() {
    const numbers = collectUniqueTechDocumentNumbers(rows.value)
    checking.value = true
    progress.value = { completed: 0, total: numbers.length }
    try {
      const results = await mapWithConcurrencyLimit(numbers, CONCURRENCY_LIMIT, checkOne)
      reportResults(results.filter((result) => result).length, results.length)
    } finally {
      checking.value = false
    }
  }

  async function checkOne(number: string) {
    issueValues.value[number] = null
    try {
      issueValues.value[number] = String(await searchWithRetry(number))
      return true
    } catch {
      issueValues.value[number] = undefined
      return false
    } finally {
      progress.value.completed += 1
    }
  }

  async function searchWithRetry(number: string): Promise<unknown> {
    for (let attempt = 0; attempt <= RETRY_LIMIT; attempt++) {
      try {
        return await proofStore.search(number)
      } catch (error) {
        if (attempt === RETRY_LIMIT) throw error
        await waitForRetry(RETRY_DELAY_MILLISECONDS * (attempt + 1))
      }
    }
  }

  return { checking, progress, checkAll }
}

function reportResults(successCount: number, total: number) {
  window.$message.info(
    `Checking the issues is over! Success: ${successCount}, Fail: ${total - successCount}`
  )
}
