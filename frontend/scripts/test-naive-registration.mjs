import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import test from 'node:test'

const sourceRoot = join(process.cwd(), 'src')
const pluginPath = join(sourceRoot, 'plugins/naiveUi.ts')
const customTags = new Set(['input-width', 'search'])

test('registers every template Naive UI component explicitly', () => {
  const expected = templateTags().map(componentName).sort()
  const registered = registeredComponents().sort()
  assert.deepEqual(registered, expected)
})

test('prevents the full Naive UI plugin from returning', () => {
  const mainSource = read(join(sourceRoot, 'main.ts'))
  assert.doesNotMatch(mainSource, /import\s+naive\s+from\s+['"]naive-ui['"]/)
  assert.doesNotMatch(mainSource, /app\.use\(naive\)/)
  assert.match(mainSource, /app\.use\(naiveUi\)/)
})

function templateTags() {
  const tags = vueFiles().flatMap((file) => [...read(file).matchAll(/<n-([a-z0-9-]+)/g)])
  return [...new Set(tags.map((match) => match[1]).filter((tag) => !customTags.has(tag)))]
}

function componentName(tag) {
  const suffix = tag.split('-').map(capitalize).join('')
  return `N${suffix}`
}

function capitalize(value) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function registeredComponents() {
  const source = read(pluginPath)
  const match = source.match(/NAIVE_UI_COMPONENTS\s*=\s*\[([\s\S]*?)\]\s*as const/)
  assert.ok(match, `Component allowlist missing in ${relative(sourceRoot, pluginPath)}`)
  return [...match[1].matchAll(/\bN[A-Za-z0-9]+\b/g)].map((entry) => entry[0])
}

function vueFiles() {
  return walk(sourceRoot).filter((file) => file.endsWith('.vue'))
}

function walk(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

function read(file) {
  return readFileSync(file, 'utf8')
}
