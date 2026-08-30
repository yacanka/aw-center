import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import test from 'node:test'

const sourceRoot = join(process.cwd(), 'src')
const featureRoot = join(sourceRoot, 'features')
const featureNames = [
  'attention',
  'compliance',
  'dcc',
  'integrations',
  'jobs',
  'organization',
  'projects',
  'session',
  'tools'
]

test('keeps the frontend inside app, shared, and explicit feature roots', () => {
  assert.equal(existsSync(join(sourceRoot, 'app')), true)
  assert.equal(existsSync(join(sourceRoot, 'shared')), true)
  featureNames.forEach((name) => assert.equal(existsSync(join(featureRoot, name)), true, name))

  const legacyRoots = [
    'components',
    'composables',
    'config',
    'models',
    'plugins',
    'router',
    'services',
    'stores',
    'types',
    'utils',
    'views'
  ]
  const populated = legacyRoots.filter((name) => sourceFiles(join(sourceRoot, name)).length > 0)
  assert.deepEqual(populated, [])
})

test('components and pages never bypass feature APIs with an HTTP client', () => {
  const presentationFiles = sourceFiles(sourceRoot).filter((file) =>
    /\/(components|pages|layouts)\//.test(file)
  )
  const offenders = presentationFiles.filter((file) =>
    /from\s+['"](?:axios|@\/shared\/api\/http)['"]/.test(read(file))
  )
  assert.deepEqual(
    offenders.map((file) => relative(sourceRoot, file)),
    []
  )
})

test('keeps feature stores out of the global window namespace', () => {
  const offenders = sourceFiles(sourceRoot).filter((file) =>
    /window\.\$(?:compdocStore|dccStore|ddfStore|orgsStore|outlookStore)/.test(read(file))
  )
  const declarations = read(join(sourceRoot, 'shared/types/global.d.ts'))

  assert.deepEqual(
    offenders.map((file) => relative(sourceRoot, file)),
    []
  )
  assert.doesNotMatch(declarations, /\$(?:compdocStore|dccStore|ddfStore|orgsStore|outlookStore)/)
})

test('limits Pinia to application-lifetime state', () => {
  const piniaStores = sourceFiles(sourceRoot)
    .filter((file) => /\bdefineStore\s*\(/.test(read(file)))
    .map((file) => relative(sourceRoot, file))
    .sort()

  assert.deepEqual(piniaStores, [
    'app/stores/popupStore.js',
    'app/stores/releaseNotes.ts',
    'features/dcc/stores/dcc.ts',
    'features/projects/stores/projectCatalog.ts',
    'features/session/stores/session.ts'
  ])
})

test('does not cache browser identity or credentials', () => {
  const sessionSource = read(join(featureRoot, 'session/stores/session.ts'))
  const storageSource = read(join(sourceRoot, 'shared/services/storage.ts'))
  const sources = sourceFiles(sourceRoot).map(read).join('\n')

  assert.doesNotMatch(sessionSource, /localStorage|sessionStorage|readString|readJson/)
  assert.doesNotMatch(
    storageSource,
    /jira_session_id|LEGACY_CREDENTIAL_KEYS|clearLegacyCredentialStorage/
  )
  assert.doesNotMatch(
    sources,
    /localStorage\.(?:getItem|setItem)\([^\n]*(?:token|JSESSION|credential)/i
  )
})

test('keeps project capabilities server-owned and fail-closed', () => {
  const projectApi = read(join(featureRoot, 'projects/api/projectRegistry.ts'))
  const catalog = read(join(featureRoot, 'projects/stores/projectCatalog.ts'))
  const sources = `${projectApi}\n${catalog}`

  assert.doesNotMatch(sources, /STATIC_PROJECT|fallbackProjects|defaultProjects/i)
  assert.match(catalog, /status/)
  assert.match(catalog, /error/)
})

test('preserves corrected organization and presentation mutation targets', () => {
  const organizationSource = read(join(featureRoot, 'organization/api/organizationProjects.ts'))
  const presentationSource = read(join(featureRoot, 'tools/composables/presentationController.ts'))
  assert.match(organizationSource, /state\.responsibles = state\.responsibles\.filter/)
  assert.match(presentationSource, /API_PATHS\.presentations}\/slides\/\$\{id}/)
})

test('keeps registered projects read-only in organization screens', () => {
  const controller = read(join(featureRoot, 'organization/composables/organizationController.ts'))
  const requests = read(join(featureRoot, 'organization/api/organizationProjects.ts'))
  const projectView = read(join(featureRoot, 'organization/pages/Projects.vue'))

  assert.doesNotMatch(controller, /(create|update|delete)Project\(/)
  assert.doesNotMatch(requests, /\.(post|put|patch|delete)\([^\n]*projects/)
  assert.doesNotMatch(projectView, /ProjectsPopup|New Project/)
  assert.match(projectView, /project\.capabilities/)
  assert.match(projectView, /project\.roles/)
})

function sourceFiles(directory) {
  if (!existsSync(directory)) return []
  return walk(directory).filter((file) => /\.(ts|js|vue)$/.test(file))
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
