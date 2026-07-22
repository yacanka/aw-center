import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import test from 'node:test'

const sourceRoot = join(process.cwd(), 'src')
const storeRoot = join(sourceRoot, 'stores')
const domainStores = [
  'dcc.ts',
  'ddf.ts',
  'docproof.ts',
  'doors.ts',
  'excel.ts',
  'organizations.ts',
  'outlook.ts',
  'presentations.ts'
]

test('keeps integration stores in explicit domain modules', () => {
  assert.equal(existsSync(join(storeRoot, 'api.ts')), false)
  assert.equal(existsSync(join(storeRoot, 'datatable.ts')), false)
  domainStores.forEach((file) => assert.equal(existsSync(join(storeRoot, file)), true, file))
})

test('prevents the removed API-store facade from returning', () => {
  const offenders = sourceFiles().filter((file) => /@\/stores\/(api|datatable)['"]/.test(read(file)))
  assert.deepEqual(offenders.map((file) => relative(sourceRoot, file)), [])
})

test('prevents the removed delayed CompDoc feature flag from returning', () => {
  const featureFlagPath = join(sourceRoot, 'services', 'featureFlags.ts')
  const offenders = sourceFiles().filter((file) =>
    /VITE_SHOW_DELAYED_COMPDOCS|SHOW_DELAYED_COMPDOCS|services\/featureFlags/.test(read(file))
  )

  assert.equal(existsSync(featureFlagPath), false)
  assert.deepEqual(
    offenders.map((file) => relative(sourceRoot, file)),
    []
  )
})

test('keeps every new integration store below the repository size limit', () => {
  const tableModules = [
    join(sourceRoot, 'components/table/advancedFilterMenus.ts'),
    join(sourceRoot, 'components/table/valueFilterMenus.ts'),
    join(sourceRoot, 'services/compdocCatalog.ts'),
    join(sourceRoot, 'services/tableFilters.ts')
  ]
  const candidates = [...domainStores.map((file) => join(storeRoot, file)), ...tableModules]
  const oversized = candidates.filter((file) => lineCount(file) > 200)
  assert.deepEqual(oversized, [])
})

test('preserves corrected organization and presentation mutation targets', () => {
  const organizationSource = read(join(storeRoot, 'organizationProjects.ts'))
  const presentationSource = read(join(storeRoot, 'presentations.ts'))
  assert.match(organizationSource, /state\.responsibles = state\.responsibles\.filter/)
  assert.match(presentationSource, /API_PATHS\.presentations}\/slides\/\$\{id}/)
})

test('keeps registered projects read-only in Organizations', () => {
  const store = read(join(storeRoot, 'organizations.ts'))
  const requests = read(join(storeRoot, 'organizationProjects.ts'))
  const projectView = read(join(sourceRoot, 'views/orgs/Projects.vue'))

  assert.doesNotMatch(store, /(create|update|delete)Project\(/)
  assert.doesNotMatch(requests, /axios\.(post|put|patch|delete)\([^\n]*projects/)
  assert.doesNotMatch(projectView, /ProjectsPopup|New Project/)
  assert.match(projectView, /project\.capabilities/)
  assert.match(projectView, /project\.enabled/)
})

function sourceFiles() {
  return walk(sourceRoot).filter((file) => /\.(ts|vue)$/.test(file))
}

function walk(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })
}

function lineCount(file) {
  return read(file).split(/\r?\n/).length
}

function read(file) {
  return readFileSync(file, 'utf8')
}
