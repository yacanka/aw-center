import { jiraCustomFieldInputTypes } from '@/features/dcc/models/jiraCustomFieldInputTypes'
import { IJiraField, JiraFieldInputType } from '@/features/dcc/models/jira'

/** Resolve the editor type for a JIRA field using custom mappings before metadata heuristics. */
export function resolveJiraFieldInputType(field: IJiraField): JiraFieldInputType {
  const configuredInputType = jiraCustomFieldInputTypes[field.id]
  if (configuredInputType) return configuredInputType

  const schemaType = String(field.schema?.type || '').toLowerCase()
  const schemaCustom = String(field.schema?.custom || '').toLowerCase()
  const schemaItems = String(field.schema?.items || '').toLowerCase()
  const fieldIdentity = `${field.id} ${field.name}`.toLowerCase()

  if (schemaType === 'datetime') return 'datetime'
  if (schemaType === 'boolean') return 'boolean'
  if (
    schemaType &&
    ![
      'string',
      'date',
      'user',
      'number',
      'integer',
      'float',
      'double',
      'array',
      'option',
      'option-with-child',
      'priority',
      'component',
      'version',
      'group'
    ].includes(schemaType)
  )
    return 'unsupported'
  if (isDateField(schemaType, fieldIdentity)) return 'date'
  if (isPersonField(schemaType, schemaCustom, schemaItems, fieldIdentity)) return 'person'
  if (isNumberField(schemaType)) return 'number'
  return 'text'
}

function isDateField(schemaType: string, fieldIdentity: string) {
  return (
    schemaType == 'date' ||
    (!schemaType && (fieldIdentity.includes('duedate') || fieldIdentity.includes('start date')))
  )
}

function isPersonField(
  schemaType: string,
  schemaCustom: string,
  schemaItems: string,
  fieldIdentity: string
) {
  return (
    schemaType == 'user' ||
    schemaItems == 'user' ||
    schemaCustom.includes('userpicker') ||
    (!schemaType && fieldIdentity.includes('assignee'))
  )
}

function isNumberField(schemaType: string) {
  return ['number', 'integer', 'float', 'double'].includes(schemaType)
}

/** Extract an issue reference without rendering it as [object Object]. */
export function jiraInputToken(value: unknown): string | number | null {
  if (typeof value === 'boolean') return String(value)
  if (typeof value === 'string' || typeof value === 'number') return value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const reference = value as Record<string, unknown>
  for (const key of ['id', 'accountId', 'name', 'key', 'value']) {
    const token = reference[key]
    if (typeof token === 'string' || typeof token === 'number') return token
  }
  return null
}
