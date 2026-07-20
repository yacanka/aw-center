import assert from 'node:assert/strict'
import test from 'node:test'

class TestFile {
  constructor(parts, name, options) {
    this.parts = parts
    this.name = name
    this.type = options.type
  }
}

globalThis.File = TestFile

const {
  isPdfAttachment,
  loadOutlookPdfAttachments,
  selectOutlookPdfInputs,
  validateOutlookDownloadUrl,
  validatePdfBlob
} = await import('../src/services/outlookAttachmentFiles.ts')

const pdfAttachment = {
  name: 'change.pdf',
  size: 9,
  mime: 'application/pdf',
  download_url: '/outlook/msg/download/?token=private&index=0'
}

test('loads PDF attachments sequentially and reports isolated failures', async () => {
  const calls = []
  const result = await loadOutlookPdfAttachments(
    [pdfAttachment, { ...pdfAttachment, name: 'notes.txt' }, { ...pdfAttachment, name: 'bad.pdf' }],
    async (attachment) => {
      calls.push(attachment.name)
      if (attachment.name === 'bad.pdf') throw new Error('expired')
      return new TestFile([], attachment.name, { type: attachment.mime })
    }
  )

  assert.deepEqual(calls, ['change.pdf', 'bad.pdf'])
  assert.equal(result.files[0].name, 'change.pdf')
  assert.deepEqual(result.failures, [{ name: 'bad.pdf', reason: 'expired' }])
})

test('accepts case-insensitive PDF names and rejects cross-origin links', () => {
  assert.equal(isPdfAttachment({ ...pdfAttachment, name: 'CHANGE.PDF' }), true)
  assert.throws(
    () => validateOutlookDownloadUrl('https://attacker.test/outlook/msg/download/?token=x'),
    /invalid/
  )
})

test('manual PDF replaces an expired attachment with the same name', () => {
  const manual = new TestFile([], 'CHANGE.PDF', { type: 'application/pdf' })
  const selected = selectOutlookPdfInputs(
    { files: [], failures: [{ name: 'change.pdf', reason: 'expired' }] },
    [manual]
  )

  assert.deepEqual(selected.files, [manual])
  assert.deepEqual(selected.failures, [])
})

test('verifies attachment size and PDF signature', async () => {
  const blob = new Blob(['%PDF-safe'])

  await validatePdfBlob(blob, blob.size)
  await assert.rejects(() => validatePdfBlob(blob, blob.size + 1), /size check/)
  await assert.rejects(() => validatePdfBlob(new Blob(['not-pdf']), 7), /valid PDF/)
})
