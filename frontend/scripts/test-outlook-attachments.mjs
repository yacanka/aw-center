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
  validateOutlookDownloadCapability,
  validatePdfBlob
} = await import('../src/features/tools/api/outlookAttachmentPolicy.ts')

const pdfAttachment = {
  name: 'change.pdf',
  size: 9,
  mime: 'application/pdf',
  download_capability: 'A'.repeat(48)
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

test('accepts case-insensitive PDF names and rejects malformed capabilities', () => {
  assert.equal(isPdfAttachment({ ...pdfAttachment, name: 'CHANGE.PDF' }), true)
  assert.equal(validateOutlookDownloadCapability('A'.repeat(48)), 'A'.repeat(48))
  assert.throws(() => validateOutlookDownloadCapability('short'), /invalid/)
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
