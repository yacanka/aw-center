import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { publishRenderer } from './build-mermaid-renderer.mjs'

test('publishes complete renderer files without removing the file observed by concurrent builds', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'aw-mermaid-output-'))
  const previous = '/* previous renderer */' + 'a'.repeat(1024 * 1024)
  const next = '/* next renderer */' + 'b'.repeat(1024 * 1024)
  try {
    await publishRenderer(previous, directory)
    let writing = true
    const writes = Promise.all(
      Array.from({ length: 12 }, (_, index) =>
        publishRenderer(index % 2 ? previous : next, directory)
      )
    ).finally(() => {
      writing = false
    })
    do {
      const observed = await readFile(join(directory, 'renderer.js'), 'utf8')
      assert.ok(
        observed === previous || observed === next,
        'readers must never see missing or partially written renderer output'
      )
    } while (writing)
    await writes
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
