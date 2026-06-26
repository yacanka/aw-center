import { jiraCustomFieldInputTypes } from '@/config/jiraCustomFieldInputTypes'
import { IJiraField, JiraFieldInputType } from '@/models/jira'

/** Resolve the editor type for a JIRA field using custom mappings before metadata heuristics. */
export function resolveJiraFieldInputType(field: IJiraField): JiraFieldInputType {
  const configuredInputType = jiraCustomFieldInputTypes[field.id]
  if (configuredInputType) return configuredInputType

  const schemaType = String(field.schema?.type || '').toLowerCase()
  const schemaCustom = String(field.schema?.custom || '').toLowerCase()
  const schemaItems = String(field.schema?.items || '').toLowerCase()
  const fieldIdentity = `${field.id} ${field.name}`.toLowerCase()

  if (isDateField(schemaType, fieldIdentity)) return 'date'
  if (isPersonField(schemaType, schemaCustom, schemaItems, fieldIdentity)) return 'person'
  if (isNumberField(schemaType)) return 'number'
  return 'text'
}

function isDateField(schemaType: string, fieldIdentity: string) {
  return schemaType == 'date' || fieldIdentity.includes('duedate') || fieldIdentity.includes('start date')
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
    fieldIdentity.includes('assignee')
  )
}

function isNumberField(schemaType: string) {
  return ['number', 'integer', 'float', 'double'].includes(schemaType)
}
