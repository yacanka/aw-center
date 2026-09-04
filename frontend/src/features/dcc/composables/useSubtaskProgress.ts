import { computed, ref, watch } from 'vue'
import { usePageJob } from '@/features/jobs/composables/usePageJob'
import { isActiveJobStatus, type Job } from '@/features/jobs/api/jobs'
import { resumeSubtaskJob } from '@/features/dcc/api/jiraSubtasks'
import { formatApiError } from '@/shared/api/apiError'

type ProgressStatus = 'default' | 'success' | 'warning' | 'error'

/** Render durable job updates in the original generator's progress bar. */
export function useSubtaskProgress(queryKey: 'subtask_job' | 'excel_subtask_job') {
  const { job, active, errorMessage, setJob } = usePageJob(queryKey)
  const submitting = ref(false)
  const loadingBar = ref({
    show: false,
    status: 'success' as ProgressStatus,
    percentage: 0,
    content: ''
  })
  const busy = computed(() => submitting.value || active.value)
  let notifiedResult = ''

  function notify(status: Exclude<ProgressStatus, 'default'>, description: string): void {
    window.$notification[status]({
      title: status[0].toUpperCase() + status.slice(1),
      description,
      duration: 3000
    })
  }

  watch(job, (current) => {
    if (!current) return
    if (current.kind !== 'dcc.create_jira_subtasks') {
      loadingBar.value = {
        show: true,
        status: 'error',
        percentage: 0,
        content: 'This is not a subtask job.'
      }
      return
    }
    const status: ProgressStatus = isActiveJobStatus(current.status)
      ? 'default'
      : current.status === 'succeeded'
        ? 'success'
        : current.status === 'cancelled'
          ? 'warning'
          : 'error'
    loadingBar.value = {
      show: true,
      status,
      percentage: status === 'success' ? 100 : current.progress,
      content: status === 'default' ? current.message : ''
    }
    const result = `${current.id}:${current.status}`
    if (status !== 'default' && notifiedResult !== result) {
      notifiedResult = result
      notify(status, current.message)
    }
  })

  watch(errorMessage, (message) => {
    if (!message) return
    loadingBar.value.status = 'error'
    loadingBar.value.content = message
    notify('error', message)
  })

  async function enqueue(action: () => Promise<Job>): Promise<void> {
    if (busy.value) return
    submitting.value = true
    loadingBar.value = {
      show: true,
      status: 'default',
      percentage: 0,
      content: 'Preparing subtask creation...'
    }
    try {
      setJob(await action())
    } catch (error) {
      loadingBar.value.status = 'error'
      loadingBar.value.content = ''
      notify('error', formatApiError(error))
    } finally {
      submitting.value = false
    }
  }

  async function submit(action: () => Promise<Job>): Promise<void> {
    if (busy.value) return
    const previous = job.value
    if (
      previous?.kind === 'dcc.create_jira_subtasks' &&
      ['failed', 'reconciliation_required', 'cancelled'].includes(previous.status)
    ) {
      const resumable = previous.status !== 'cancelled'
      window.$dialog.warning({
        title: 'Previous subtask batch',
        content: resumable
          ? 'The previous batch may have created subtasks. Resume checks its markers and uses the original rows, not your current edits. Creating a new batch uses the current form and may duplicate existing subtasks. Close this dialog to cancel.'
          : 'The cancelled batch may have created subtasks. Creating a new batch uses the current form and may duplicate them. Close this dialog to cancel.',
        positiveText: resumable ? 'Resume previous batch' : 'Create new batch',
        negativeText: resumable ? 'Create new batch' : 'Cancel',
        onPositiveClick: () => enqueue(resumable ? () => resumeSubtaskJob(previous.id) : action),
        onNegativeClick: resumable ? () => enqueue(action) : undefined
      })
      return
    }
    await enqueue(action)
  }

  return { loadingBar, busy, submit }
}
