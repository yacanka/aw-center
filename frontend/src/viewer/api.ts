import { parseCompdocDashboard } from '@/features/compliance/models/parseCompdocDashboard'

export interface ViewerSource {
  projects: Array<{ slug: string; name: string }>
  source_kind: 'local' | 'backup'
  read_at: string
  warning: string
}

export interface ViewerDocument {
  id: string
  name: string
  number: string | null
  status: string
  panel: string
  panel_id: string
  ata: string
  cat: string | null
  trimmed_cat: string
  delivery_bucket: string
  moc: string | null
  issue: string | null
  cover_page_no: string | null
  cover_page_issue: string | null
  target_date: string | null
  revised_target_date: string | null
  release_date: string | null
  next_action_due_date: string | null
}

async function read(path: string, method: 'GET' | 'POST', signal: AbortSignal) {
  const session = document.querySelector<HTMLMetaElement>('meta[name="dashboard-session"]')?.content
  if (!session || session === '__DASHBOARD_SESSION__')
    throw new Error('Görüntüleyiciyi masaüstü uygulamasından açın.')
  const response = await fetch(path, {
    method,
    headers: { 'X-Dashboard-Session': session, Accept: 'application/json' },
    redirect: 'error',
    credentials: 'same-origin',
    cache: 'no-store',
    signal
  })
  if (!response.ok) {
    if (response.status === 403) throw new Error('Oturumu masaüstü uygulamasından yeniden açın.')
    if (response.status === 409) {
      const problem = await response.json().catch(() => null)
      if (typeof problem?.detail === 'string') throw new Error(problem.detail)
    }
    throw new Error(
      'Veri kaynağı okunamadı. Masaüstü uygulamasındaki kaynak seçimini kontrol edin.'
    )
  }
  return response.json()
}

export async function readSource(signal: AbortSignal, refresh = false): Promise<ViewerSource> {
  const result = refresh
    ? await read('/viewer/refresh', 'POST', signal)
    : await read('/viewer/projects', 'GET', signal)
  if (!Array.isArray(result?.projects))
    throw new Error(result?.warning || 'Masaüstü uygulamasından bir veri kaynağı seçin.')
  return result
}

export async function readDashboard(project: string, signal: AbortSignal) {
  return parseCompdocDashboard(
    await read(`/viewer/projects/${encodeURIComponent(project)}/dashboard`, 'GET', signal)
  )
}

export async function readDocuments(
  project: string,
  signal: AbortSignal
): Promise<ViewerDocument[]> {
  return read(`/viewer/projects/${encodeURIComponent(project)}/documents`, 'GET', signal)
}
