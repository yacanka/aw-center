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
  result_mode: DoorsResultMode
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

export type DoorsLoop = 'module' | 'entire' | 'all' | 'document'
export type DoorsPosition = 'first' | 'after' | 'before' | 'below' | 'below_last'
export type DoorsResultMode = 'file' | 'application_result'
export type DoorsScalarAttributes = Record<string, string | number | boolean | null>

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

/** Verifies that a fixed DXL payload round-trips through Application.Result. */
export async function probeDoorsApplicationResult() {
  return (
    await axios.post<{ available: boolean; result_mode: DoorsResultMode; lines: string[] }>(
      'doors/application-result/probe/'
    )
  ).data
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
export async function fetchDoorsObjects(
  modulePath: string,
  attributes: string[],
  limit: number,
  loop: DoorsLoop = 'entire'
) {
  return (
    await axios.post<DoorsObjectList>('doors/objects/', {
      module_path: modulePath,
      attributes,
      loop,
      limit
    })
  ).data
}

/** Returns one DOORS object by absolute number. */
export async function fetchDoorsObject(
  modulePath: string,
  absoluteNumber: number,
  attributes: string[]
) {
  return (
    await axios.post<DoorsObject>('doors/objects/detail/', {
      module_path: modulePath,
      absolute_number: absoluteNumber,
      attributes
    })
  ).data
}

/** Updates scalar attributes on one DOORS object. */
export async function updateDoorsObject(
  modulePath: string,
  absoluteNumber: number,
  attributes: DoorsScalarAttributes
) {
  return (
    await axios.patch<{ updated: boolean; absolute_number: number }>('doors/objects/update/', {
      module_path: modulePath,
      absolute_number: absoluteNumber,
      attributes
    })
  ).data
}

/** Creates one DOORS object relative to an existing object or at the first position. */
export async function createDoorsObject(
  modulePath: string,
  position: DoorsPosition,
  relativeAbsoluteNumber: number | undefined,
  attributes: DoorsScalarAttributes
) {
  return (
    await axios.post<DoorsObject>('doors/objects/create/', {
      module_path: modulePath,
      position,
      relative_absolute_number: relativeAbsoluteNumber,
      attributes
    })
  ).data
}
