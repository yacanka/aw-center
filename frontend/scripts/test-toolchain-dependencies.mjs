import assert from 'node:assert/strict'
import test from 'node:test'
import { globSync } from 'glob'
import { minimatch } from 'minimatch'
import { parseFromFilesSync } from 'editorconfig'
import { resolve } from 'node:path'

test('typechecker source globs still support brace alternatives after security overrides', () => {
  assert.equal(minimatch('src/app/App.vue', 'src/**/*.{ts,vue}'), true)
  assert.equal(minimatch('src/app/bootstrap.ts', 'src/**/*.{ts,vue}'), true)
  assert.equal(minimatch('package.json', 'src/**/*.{ts,vue}'), false)
})

test('toolchain globs discover both Vue and TypeScript sources', () => {
  const files = globSync('src/app/*.{vue,ts}', { cwd: process.cwd(), posix: true })
  assert.ok(files.includes('src/app/App.vue'))
  assert.ok(files.includes('src/app/bootstrap.ts'))
  assert.ok(files.every((file) => /\.(vue|ts)$/.test(file)))
})

test('EditorConfig can match the Vue section used by formatter integrations', () => {
  const settings = parseFromFilesSync(resolve('src/app/App.vue'), [
    {
      name: resolve('.editorconfig'),
      contents: Buffer.from('root = true\n[*.vue]\nindent_size = 2\n')
    }
  ])
  assert.equal(settings.indent_size, 2)
})
