import assert from 'node:assert/strict'
import test from 'node:test'
import { syncBuiltinESMExports } from 'node:module'
import { createHash } from 'node:crypto'
import fsPromises, {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  symlink,
  writeFile
} from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runInNewContext } from 'node:vm'
import * as renderer from './build-mermaid-renderer.mjs'

const digest = (source) => createHash('sha256').update(source).digest('hex')
const classic = (label) => `(()=>{globalThis.renderer=${JSON.stringify(label)}})();`

async function fixture(t, { realBuild = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'aw-mermaid-cache-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const put = async (path, source) => {
    await mkdir(dirname(join(root, path)), { recursive: true })
    await writeFile(join(root, path), source)
  }
  await put(
    'src/features/mermaid/renderer/entry.ts',
    "import { value } from '../models/value'\nglobalThis.value = value"
  )
  await put('src/features/mermaid/models/value.ts', 'export const value = 1')
  await put('scripts/build.mjs', '// build identity')
  await put('package-lock.json', '{"lockfileVersion":3}')
  await put('tsconfig.json', '{"compilerOptions":{"moduleResolution":"node"}}')
  if (realBuild)
    await symlink(
      fileURLToPath(new URL('../node_modules', import.meta.url)),
      join(root, 'node_modules'),
      'junction'
    )
  else
    for (const name of ['vite', 'rolldown', 'typescript'])
      await put(`node_modules/${name}/package.json`, JSON.stringify({ name, version: '1.0.0' }))
  let builds = 0
  const options = {
    rootDirectory: root,
    outputDirectory: join(root, '.cache/mermaid'),
    scriptFiles: [join(root, 'scripts/build.mjs')],
    buildOperation: realBuild ? undefined : async () => classic(`build-${++builds}`),
    log: () => {}
  }
  const run = (overrides = {}) => renderer.prepareRenderer({ ...options, ...overrides })
  const output = () => readFile(join(options.outputDirectory, 'renderer.js'), 'utf8')
  const receipt = async () =>
    JSON.parse(await readFile(join(options.outputDirectory, 'receipt.json'), 'utf8'))
  return { root, put, run, output, receipt, options, builds: () => builds }
}

test('explicit dev mode reuses the verified bytes without running a second build', async (t) => {
  const f = await fixture(t)
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await f.output(), classic('build-1'))
  assert.equal(await f.run({ dev: true }), 'reused')
  assert.equal(f.builds(), 1)
})

test('build-tool normalization of requested options does not invalidate the input snapshot', async (t) => {
  const f = await fixture(t)
  assert.equal(
    await f.run({
      dev: true,
      buildOperation: async (options) => {
        options.worker = {}
        options.build.rollupOptions = options.build.rolldownOptions
        return classic('normalized')
      }
    }),
    'built'
  )
  assert.equal(await f.run({ dev: true }), 'reused')
  assert.equal(await f.output(), classic('normalized'))
})

test('default preparations and explicit force always build despite a valid dev receipt', async (t) => {
  const f = await fixture(t)
  await f.run({ dev: true })
  assert.equal(await f.run(), 'built')
  assert.equal(await f.run({ dev: true, force: true }), 'built')
  assert.equal(await f.output(), classic('build-3'))
})

for (const [name, change] of [
  [
    'changed renderer source',
    (f) => f.put('src/features/mermaid/renderer/entry.ts', 'globalThis.changed = true')
  ],
  [
    'changed imported source outside renderer',
    (f) => f.put('src/features/mermaid/models/value.ts', 'export const value = 2')
  ],
  [
    'added renderer input',
    (f) => f.put('src/features/mermaid/renderer/new.ts', 'export const added = 1')
  ],
  [
    'deleted renderer input',
    async (f) => {
      await rm(join(f.root, 'src/features/mermaid/renderer/extra.ts'))
    }
  ],
  ['changed lock', (f) => f.put('package-lock.json', '{"lockfileVersion":3,"changed":true}')],
  ['changed build script', (f) => f.put('scripts/build.mjs', '// new build identity')],
  [
    'changed tool version',
    (f) => f.put('node_modules/rolldown/package.json', '{"name":"rolldown","version":"2.0.0"}')
  ],
  [
    'changed TypeScript configuration',
    (f) => f.put('tsconfig.json', '{"compilerOptions":{"target":"es2024"}}')
  ]
]) {
  test(`${name} invalidates dev reuse`, async (t) => {
    const f = await fixture(t)
    await f.put('src/features/mermaid/renderer/extra.ts', 'export const extra = 1')
    await f.run({ dev: true })
    await change(f)
    assert.equal(await f.run({ dev: true }), 'built')
    assert.equal(await f.output(), classic('build-2'))
  })
}

for (const overrides of [
  { nodeVersion: 'different-node' },
  { buildOptions: { build: { target: 'es2030' } } }
]) {
  test(`${Object.keys(overrides)[0]} identity invalidates dev reuse`, async (t) => {
    const f = await fixture(t)
    await f.run({ dev: true })
    assert.equal(await f.run({ dev: true, ...overrides }), 'built')
    assert.equal(await f.output(), classic('build-2'))
  })
}

test('changes to an extended TypeScript configuration invalidate dev reuse', async (t) => {
  const f = await fixture(t)
  await f.put('tsconfig.base.json', '{"compilerOptions":{"target":"es2022"}}')
  await f.put('tsconfig.json', '{"extends":"./tsconfig.base.json"}')
  await f.run({ dev: true })
  await f.put('tsconfig.base.json', '{"compilerOptions":{"target":"es2024"}}')
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await f.output(), classic('build-2'))
})

test('added higher-priority imported file changes the resolved local input set', async (t) => {
  const f = await fixture(t)
  await rm(join(f.root, 'src/features/mermaid/models/value.ts'))
  await f.put('src/features/mermaid/models/value.js', 'export const value = 1')
  await f.run({ dev: true })
  await f.put('src/features/mermaid/models/value.ts', 'export const value = 2')
  assert.equal(await f.run({ dev: true }), 'built')
})

async function runtimeValue(f) {
  const context = {}
  runInNewContext(await f.output(), context)
  return context.value
}

test('real Vite invalidates an added JS sibling which overrides an extensionless TS import', async (t) => {
  const f = await fixture(t, { realBuild: true })
  await f.run({ dev: true })
  assert.equal(await runtimeValue(f), 1)
  assert.equal(
    await f.run({ dev: true }),
    'reused',
    'missing optional candidates must allow a warm hit'
  )
  await f.put('src/features/mermaid/models/value.js', 'export const value = 2')
  const result = await f.run({ dev: true })
  const cachedValue = await runtimeValue(f)
  await f.run({ dev: true, force: true })
  assert.equal(
    await runtimeValue(f),
    2,
    'the real builder must demonstrate the JS candidate takes precedence'
  )
  assert.equal(
    cachedValue,
    2,
    'dev preparation must produce the same runtime value as a forced build'
  )
  assert.equal(result, 'built')
})

for (const specifier of ['../models/value', '../models/value.js']) {
  test(`real Vite invalidates edits to runtime JS when TypeScript resolves TS: ${specifier}`, async (t) => {
    const f = await fixture(t, { realBuild: true })
    await f.put(
      'src/features/mermaid/renderer/entry.ts',
      `import { value } from '${specifier}'\nglobalThis.value = value`
    )
    await f.put('src/features/mermaid/models/value.js', 'export const value = 2')
    await f.run({ dev: true })
    assert.equal(await runtimeValue(f), 2)
    await f.put('src/features/mermaid/models/value.js', 'export const value = 3')
    assert.equal(await f.run({ dev: true }), 'built')
    assert.equal(await runtimeValue(f), 3)
    assert.equal(await f.run({ dev: true }), 'reused')
    await rm(join(f.root, 'src/features/mermaid/models/value.js'))
    assert.equal(await f.run({ dev: true }), 'built')
    assert.equal(await runtimeValue(f), 1)
  })
}

test('real Vite may use valid JS while an unused TS alternative has an unresolved import', async (t) => {
  const f = await fixture(t, { realBuild: true })
  await f.put('src/features/mermaid/models/value.ts', "export { value } from './not-used'")
  await f.put('src/features/mermaid/models/value.js', 'export const value = 51')
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await runtimeValue(f), 51)
  assert.equal(await f.run({ dev: true }), 'reused')
  await f.put('src/features/mermaid/models/not-used.js', 'export const value = 52')
  assert.equal(
    await f.run({ dev: true }),
    'built',
    'new local candidates must still invalidate the conservative key'
  )
  assert.equal(await runtimeValue(f), 51)
})

test('real Vite fingerprints transitive imports of the runtime JS candidate outside renderer', async (t) => {
  const f = await fixture(t, { realBuild: true })
  await f.put('src/features/mermaid/models/value.js', "export { value } from '../runtime/nested'")
  await f.put('src/features/mermaid/runtime/nested.js', 'export const value = 11')
  await f.run({ dev: true })
  assert.equal(await runtimeValue(f), 11)
  await f.put('src/features/mermaid/runtime/nested.js', 'export const value = 12')
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await runtimeValue(f), 12)
})

for (const [specifier, initial, changed, expected] of [
  ['../assets/value.json', '{"value":31}', '{"value":32}', 32],
  ['../assets/icon.svg?raw', '<svg>before</svg>', '<svg>after</svg>', '<svg>after</svg>']
]) {
  test(`real Vite fingerprints runtime asset bytes: ${specifier}`, async (t) => {
    const f = await fixture(t, { realBuild: true })
    await f.put(
      'src/features/mermaid/renderer/entry.ts',
      `import asset from '${specifier}'\nglobalThis.value = ${specifier.endsWith('.json') ? 'asset.value' : 'asset'}`
    )
    const path = 'src/features/mermaid/assets/' + specifier.split('/').at(-1).split('?')[0]
    await f.put(path, initial)
    await f.run({ dev: true })
    await f.put(path, changed)
    assert.equal(await f.run({ dev: true }), 'built')
    assert.equal(await runtimeValue(f), expected)
    assert.equal(await f.run({ dev: true }), 'reused')
  })
}

test('real Vite fingerprints a local package runtime entry outside its declaration directory', async (t) => {
  const f = await fixture(t, { realBuild: true })
  await rm(join(f.root, 'src/features/mermaid/models/value.ts'))
  await f.put(
    'src/features/mermaid/models/value/package.json',
    '{"main":"../runtime.js","types":"value.d.ts"}'
  )
  await f.put('src/features/mermaid/models/value/value.d.ts', 'export declare const value: number')
  await f.put('src/features/mermaid/models/runtime.js', 'export const value = 41')
  await f.run({ dev: true })
  assert.equal(await runtimeValue(f), 41)
  await f.put('src/features/mermaid/models/runtime.js', 'export const value = 42')
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await runtimeValue(f), 42)
})

test('real Vite fingerprints a local package runtime entry when TypeScript selects its declarations', async (t) => {
  const f = await fixture(t, { realBuild: true })
  await rm(join(f.root, 'src/features/mermaid/models/value.ts'))
  await f.put(
    'src/features/mermaid/models/value/package.json',
    '{"main":"runtime.js","types":"value.d.ts"}'
  )
  await f.put('src/features/mermaid/models/value/value.d.ts', 'export declare const value: number')
  await f.put('src/features/mermaid/models/value/runtime.js', 'export const value = 21')
  await f.run({ dev: true })
  assert.equal(await runtimeValue(f), 21)
  await f.put('src/features/mermaid/models/value/runtime.js', 'export const value = 22')
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await runtimeValue(f), 22)
})

for (const [name, corrupt] of [
  ['missing output', (f) => rm(join(f.options.outputDirectory, 'renderer.js'))],
  [
    'corrupt output',
    (f) => writeFile(join(f.options.outputDirectory, 'renderer.js'), classic('corrupt'))
  ],
  ['missing receipt', (f) => rm(join(f.options.outputDirectory, 'receipt.json'))],
  ['invalid receipt', (f) => writeFile(join(f.options.outputDirectory, 'receipt.json'), '{partial')]
]) {
  test(`${name} causes a rebuild`, async (t) => {
    const f = await fixture(t)
    await f.run({ dev: true })
    await corrupt(f)
    assert.equal(await f.run({ dev: true }), 'built')
    assert.equal(await f.output(), classic('build-2'))
  })
}

test('matching digest cannot authorize output containing runtime imports', async (t) => {
  const f = await fixture(t)
  await f.run({ dev: true })
  const source = 'import("./runtime.js")'
  const receipt = await f.receipt()
  receipt.outputDigest = digest(source)
  await writeFile(join(f.options.outputDirectory, 'renderer.js'), source)
  await writeFile(join(f.options.outputDirectory, 'receipt.json'), JSON.stringify(receipt))
  assert.equal(await f.run({ dev: true }), 'built')
})

for (const source of [
  '',
  'import("./runtime.js")',
  'import /* comment */ ("./runtime.js")',
  'import x from "./runtime.js"',
  'export const value = 1'
]) {
  test(`build rejects a non-classic or empty renderer: ${JSON.stringify(source)}`, async (t) => {
    const f = await fixture(t)
    await assert.rejects(
      f.run({ buildOperation: async () => source }),
      /self-contained classic script/
    )
    await assert.rejects(f.receipt(), { code: 'ENOENT' })
  })
}

test('failed and cancelled builds cannot publish a success receipt', async (t) => {
  const f = await fixture(t)
  await assert.rejects(
    f.run({
      buildOperation: async () => {
        throw new Error('build failed')
      }
    }),
    /build failed/
  )
  await assert.rejects(f.receipt(), { code: 'ENOENT' })
  const controller = new AbortController()
  await assert.rejects(
    f.run({
      signal: controller.signal,
      buildOperation: async () => {
        controller.abort()
        return classic('cancelled')
      }
    }),
    { name: 'AbortError' }
  )
  await assert.rejects(f.receipt(), { code: 'ENOENT' })
})

test('inputs changed during a build are rejected before publishing output or receipt', async (t) => {
  const f = await fixture(t)
  await assert.rejects(
    f.run({
      buildOperation: async () => {
        await f.put('src/features/mermaid/models/value.ts', 'export const value = 9')
        return classic('stale')
      }
    }),
    /inputs changed/
  )
  await assert.rejects(f.output(), { code: 'ENOENT' })
  await assert.rejects(f.receipt(), { code: 'ENOENT' })
  assert.equal(await f.run({ dev: true }), 'built')
})

test('a source change while output is staged cannot publish a success receipt', async (t) => {
  const f = await fixture(t)
  await mkdir(f.options.outputDirectory, { recursive: true })
  let changed = false
  const originalWriteFile = fsPromises.writeFile
  // Edit after the real staging write; directory notifications can arrive after publication.
  t.mock.method(fsPromises, 'writeFile', async (path, ...args) => {
    const result = await originalWriteFile(path, ...args)
    if (!changed && dirname(path) === f.options.outputDirectory && /renderer-.*\.tmp$/.test(path)) {
      changed = true
      await originalWriteFile(
        join(f.root, 'src/features/mermaid/models/value.ts'),
        'export const value = 99'
      )
    }
    return result
  })
  syncBuiltinESMExports()
  t.after(() => {
    t.mock.restoreAll()
    syncBuiltinESMExports()
  })
  const source = classic('staged')
  await assert.rejects(f.run({ buildOperation: async () => source }), /inputs changed/)
  assert.equal(changed, true, 'the source edit must occur during temporary output staging')
  await assert.rejects(f.receipt(), { code: 'ENOENT' })
})

test('interrupted publication leaves an untrusted pair that the next dev preparation rebuilds', async (t) => {
  const f = await fixture(t)
  await mkdir(join(f.options.outputDirectory, 'receipt.json'), { recursive: true })
  await assert.rejects(f.run())
  assert.equal(await f.output(), classic('build-1'))
  await rm(join(f.options.outputDirectory, 'receipt.json'), { recursive: true })
  assert.equal(await f.run({ dev: true }), 'built')
  assert.equal(await f.output(), classic('build-2'))
  assert.deepEqual((await readdir(f.options.outputDirectory)).sort(), [
    'receipt.json',
    'renderer.js'
  ])
})

test('concurrent builds bind receipts to their generated bytes rather than rereading another output', async (t) => {
  const f = await fixture(t)
  await Promise.all(
    Array.from({ length: 12 }, (_, index) =>
      f.run({ buildOperation: async () => classic(`concurrent-${index}`) })
    )
  )
  const observed = await f.output()
  const receipt = await f.receipt()
  const result = await f.run({ dev: true })
  if (receipt.outputDigest === digest(observed)) {
    assert.equal(result, 'reused')
    assert.equal(await f.output(), observed)
  } else {
    assert.equal(result, 'built', 'a mixed publication pair must never authorize reuse')
    assert.equal(await f.output(), classic('build-1'))
  }
})

test('an older concurrent build cannot publish after its input snapshot changes', async (t) => {
  const f = await fixture(t)
  let finishOld, startedOld
  const started = new Promise((resolve) => {
    startedOld = resolve
  })
  const old = f.run({
    buildOperation: async () => {
      startedOld()
      return new Promise((resolve) => {
        finishOld = resolve
      })
    }
  })
  await started
  await f.put('src/features/mermaid/models/value.ts', 'export const value = 2')
  await f.run({ dev: true })
  finishOld(classic('old'))
  await assert.rejects(old, /inputs changed/)
  assert.equal(await f.output(), classic('build-1'))
  assert.equal(await f.run({ dev: true }), 'reused')
})
