import { onMounted, ref, type Ref } from 'vue'
import { formatApiError } from '@/services/apiError'
import {
  createCustomAnalysisCheck,
  customAnalysisCheckValue,
  deleteCustomAnalysisCheck,
  fetchCustomAnalysisChecks,
  type CustomAnalysisCheck
} from '@/services/documentAnalysis'

/** Manage profile-backed custom questions and their current analysis selection. */
export function useDocumentAnalysisChecks(selectedChecks: Ref<string[]>) {
  const customChecks = ref<CustomAnalysisCheck[]>([])
  const loadingChecks = ref(false)
  const newQuestion = ref('')
  const savingQuestion = ref(false)

  async function loadQuestions(): Promise<void> {
    loadingChecks.value = true
    try {
      customChecks.value = await fetchCustomAnalysisChecks()
    } catch (error) {
      window.$message.error(formatApiError(error))
    } finally {
      loadingChecks.value = false
    }
  }

  async function saveQuestion(): Promise<void> {
    const question = newQuestion.value.trim()
    if (!question || savingQuestion.value) return
    savingQuestion.value = true
    try {
      const check = await createCustomAnalysisCheck(question)
      customChecks.value.push(check)
      selectedChecks.value.push(customAnalysisCheckValue(check.id))
      newQuestion.value = ''
      window.$message.success('Question saved to your profile and selected.')
    } catch (error) {
      window.$message.error(formatApiError(error))
    } finally {
      savingQuestion.value = false
    }
  }

  async function removeQuestion(check: CustomAnalysisCheck): Promise<void> {
    try {
      await deleteCustomAnalysisCheck(check.id)
      customChecks.value = customChecks.value.filter((item) => item.id !== check.id)
      const value = customAnalysisCheckValue(check.id)
      selectedChecks.value = selectedChecks.value.filter((item) => item !== value)
      window.$message.success('Saved question deleted.')
    } catch (error) {
      window.$message.error(formatApiError(error))
    }
  }

  onMounted(loadQuestions)
  return { customChecks, loadingChecks, newQuestion, removeQuestion, saveQuestion, savingQuestion }
}
