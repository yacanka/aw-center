import assert from 'node:assert/strict'
import test from 'node:test'
import { formatApiError, getApiErrorCode } from '../src/services/apiError.ts'

test('reads the standard payload from an Axios-style Error object', () => {
  const error = new Error('Request failed with status code 404')
  error.response = {
    data: {
      detail: 'This invitation link is invalid.',
      code: 'INVITATION_INVALID',
      recovery_hint: 'Request a new invitation.'
    }
  }

  assert.equal(
    formatApiError(error),
    'This invitation link is invalid.\nNext step: Request a new invitation.'
  )
})

test('keeps the original message for ordinary Error objects', () => {
  assert.equal(formatApiError(new Error('Network unavailable.')), 'Network unavailable.')
})

test('extracts a stable code from an Axios-style Error object', () => {
  const error = new Error('Conflict')
  error.response = {
    data: { detail: 'The reviewed records changed.', code: 'COMPDOC_IMPORT_DATABASE_CONFLICT' }
  }

  assert.equal(getApiErrorCode(error), 'COMPDOC_IMPORT_DATABASE_CONFLICT')
  assert.equal(getApiErrorCode(new Error('Network unavailable.')), undefined)
})
