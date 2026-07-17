import axios from 'axios'

export type TeamcenterStatus = {
  configured: boolean
  auth_mode: string
  service_root: string
  tls_verification_enabled: boolean
}

export type DoorsStatus = {
  configured: boolean
  platform_supported: boolean
  prefer_active_instance: boolean
  auto_start_client: boolean
}

export type DoorsObject = {
  absolute_number: number
  identifier: string
  level: number | null
  attributes: Record<string, unknown>
}

export type DoorsObjectList = {
  count: number
  results: DoorsObject[]
}

/** Returns non-secret Teamcenter integration readiness. */
export async function fetchTeamcenterStatus() {
  return (await axios.get<TeamcenterStatus>('teamcenter/status/')).data
}

/** Verifies the configured Teamcenter account and web-tier connection. */
export async function probeTeamcenter() {
  return (await axios.post<{ connected: boolean }>('teamcenter/probe/')).data
}

/** Returns saved queries visible to the configured Teamcenter account. */
export async function fetchTeamcenterSavedQueries() {
  return (await axios.get<Record<string, unknown>>('teamcenter/saved-queries/')).data
}

/** Loads a bounded set of Teamcenter object UIDs. */
export async function loadTeamcenterObjects(uids: string[]) {
  return (await axios.post<Record<string, unknown>>('teamcenter/objects/load/', { uids })).data
}

/** Returns non-secret IBM Rational DOORS integration readiness. */
export async function fetchDoorsStatus() {
  return (await axios.get<DoorsStatus>('doors/status/')).data
}

/** Checks whether the active DOORS desktop session can read a module. */
export async function checkDoorsModule(modulePath: string) {
  return (
    await axios.post<{ accessible: boolean; module_path: string }>('doors/modules/check/', {
      module_path: modulePath
    })
  ).data
}

/** Lists a bounded set of objects from a DOORS module. */
export async function fetchDoorsObjects(modulePath: string, attributes: string[], limit: number) {
  return (
    await axios.post<DoorsObjectList>('doors/objects/', {
      module_path: modulePath,
      attributes,
      loop: 'entire',
      limit
    })
  ).data
}
