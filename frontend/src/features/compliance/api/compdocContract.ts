import type {
  CompDocFilterKind,
  ICompDoc,
  ICompDocFieldContract,
  ICompDocFieldMetadata,
  ICompDocFieldsResponse
} from '@/features/compliance/models/compdocs'

const TABLE_FIELDS = new Set([
  'panel',
  'name',
  'cover_page',
  'tech_doc_no',
  'tech_doc_issue',
  'delivered_tech_doc_issue',
  'tech_doc_no_2',
  'tech_doc_issue_2',
  'delivered_tech_doc_issue_2',
  'responsible',
  'cat',
  'moc',
  'mom_no',
  'path',
  'status',
  'ubm_target_date',
  'ubm_delivery_date',
  'next_action_due_date',
  'is_archived',
  'created_at',
  'updated_at'
])

const DEFAULT_FIELDS = new Set([
  'panel',
  'name',
  'cover_page_no',
  'cover_page_issue',
  'tech_doc_no',
  'tech_doc_issue',
  'ubm_target_date',
  'ubm_delivery_date',
  'moc',
  'status'
])

const DATE_FIELDS = new Set([
  'ubm_target_date',
  'ubm_delivery_date',
  'next_action_due_date',
  'created_at',
  'updated_at'
])

/** Normalize the canonical nested backend DTO into the existing editor/table projection. */
export function normalizeCompdoc(value: unknown): ICompDoc {
  if (!isRecord(value)) throw new Error('The compliance document response is invalid.')
  const coverPage = isRecord(value.cover_page) ? value.cover_page : {}

  return {
    ...value,
    id: stringOrUndefined(value.id),
    version: positiveNumberOrUndefined(value.version),
    project: stringValue(value.project_slug || value.project),
    panel: nullableNumber(value.panel),
    name: stringValue(value.name),
    signature_panel: stringArray(value.signature_panel),
    ata: nullableString(value.ata),
    cover_page_no: stringValue(coverPage.number),
    cover_page_issue: stringValue(coverPage.issue),
    cover_page_version: positiveNumberOrUndefined(coverPage.version),
    tech_doc_no: stringValue(value.tech_doc_no),
    tech_doc_issue: stringValue(value.tech_doc_issue),
    delivered_tech_doc_issue: stringValue(value.delivered_tech_doc_issue),
    tech_doc_no_2: stringValue(value.tech_doc_no_2),
    tech_doc_issue_2: stringValue(value.tech_doc_issue_2),
    delivered_tech_doc_issue_2: stringValue(value.delivered_tech_doc_issue_2),
    responsible: stringValue(value.responsible),
    cat: nullableString(value.cat),
    moc: nullableString(value.moc),
    mom_no: stringValue(value.mom_no),
    requirements: stringArray(value.requirements),
    status_flow: [],
    status: stringValue(value.status),
    owner: nullableNumber(value.owner),
    owner_group: nullableNumber(value.owner_group),
    next_action_due_date: nullableString(value.next_action_due_date),
    is_archived: Boolean(value.is_archived),
    archived_at: nullableString(value.archived_at),
    archive_reason: stringValue(value.archive_reason),
    ubm_target_date: nullableString(value.ubm_target_date),
    ubm_delivery_date: nullableString(value.ubm_delivery_date),
    path: stringValue(value.path),
    notes: stringValue(value.notes),
    authority_sharing_number: '',
    created_time: stringValue(value.created_at),
    history: null
  }
}

/** Adapt the deliberately small server schema to non-interactive table metadata. */
export function normalizeCompdocFields(value: unknown): ICompDocFieldsResponse {
  if (!isRecord(value) || !Array.isArray(value.fields)) {
    throw new Error('The compliance document field schema is invalid.')
  }
  const fields = value.fields.filter(isFieldContract).filter((field) => TABLE_FIELDS.has(field.key))
  return {
    schema_version: positiveNumberOrUndefined(value.schema_version) || 0,
    project: stringValue(value.project),
    fields: fields.flatMap(toFieldMetadata)
  }
}

function toFieldMetadata(field: ICompDocFieldContract): ICompDocFieldMetadata[] {
  if (field.key === 'cover_page') {
    return [
      metadata('cover_page_no', 'Cover Page No', 'text', true),
      metadata('cover_page_issue', 'Cover Page Issue', 'text', true)
    ]
  }
  return [
    metadata(
      field.key,
      field.label,
      field.filter_kind || 'none',
      Boolean(field.sortable),
      Array.isArray(field.choices) ? field.choices : [],
      typeof field.option_source === 'string' ? field.option_source : null
    )
  ]
}

function metadata(
  key: string,
  label: string,
  filterKind: CompDocFilterKind,
  sortable = false,
  choices: ICompDocFieldMetadata['choices'] = [],
  optionSource: string | null = null
): ICompDocFieldMetadata {
  return {
    key,
    label,
    type: DATE_FIELDS.has(key) ? 'DateField' : 'CharField',
    width: DATE_FIELDS.has(key) ? 140 : key === 'name' ? 240 : 160,
    filter_kind: filterKind,
    sortable,
    default_visible: DEFAULT_FIELDS.has(key),
    ellipsis: !DATE_FIELDS.has(key),
    choices,
    option_source: optionSource
  }
}

function isFieldContract(value: unknown): value is ICompDocFieldContract {
  return (
    isRecord(value) &&
    typeof value.key === 'string' &&
    typeof value.label === 'string' &&
    typeof value.required === 'boolean' &&
    typeof value.read_only === 'boolean'
  )
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) ? value : null
}

function positiveNumberOrUndefined(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : undefined
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Object.prototype.toString.call(value) === '[object Object]'
}
