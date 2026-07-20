import assert from 'node:assert/strict'
import test from 'node:test'

class TestFile {}

globalThis.File = TestFile
let notificationCount = 0
globalThis.window = {
  $message: { error: () => (notificationCount += 1) }
}

const { selectedUploadFile } = await import('../src/utils/uploads.ts')

test('empty reactive upload state stays silent when requested', () => {
  notificationCount = 0

  assert.equal(selectedUploadFile([], false), null)
  assert.equal(notificationCount, 0)
})

test('submission checks still report stale selections', () => {
  notificationCount = 0

  assert.equal(selectedUploadFile([]), null)
  assert.equal(notificationCount, 1)
})

test('valid browser files are returned without notifications', () => {
  notificationCount = 0
  const file = new TestFile()

  assert.equal(selectedUploadFile([{ file }], true), file)
  assert.equal(notificationCount, 0)
})
