import { fileURLToPath } from 'node:url'
import { join, resolve } from 'node:path'
import { prepareCachedRenderer } from './mermaid-renderer-cache.mjs'

export { publishRenderer } from './mermaid-renderer-cache.mjs'

const frontendDirectory = fileURLToPath(new URL('../', import.meta.url))

function rendererBuildOptions(entry) {
  return {
    configFile: false,
    publicDir: false,
    logLevel: 'warn',
    build: {
      write: false,
      target: 'es2024',
      lib: {
        entry,
        name: 'AWMermaidRenderer',
        formats: ['iife'],
        fileName: () => 'renderer.js'
      },
      rolldownOptions: { output: { codeSplitting: false } }
    }
  }
}

async function generateRenderer(options) {
  // A cache hit does not load Vite or traverse installed dependency sources.
  const { build } = await import('vite')
  const result = await build(options)
  const output = (Array.isArray(result) ? result : [result]).flatMap((bundle) => bundle.output)
  if (output.length !== 1 || output[0].type !== 'chunk')
    throw new Error('Mermaid renderer must be a single self-contained classic script.')
  return output[0].code
}

export async function prepareRenderer({
  rootDirectory = frontendDirectory,
  outputDirectory = join(rootDirectory, '.cache/mermaid'),
  entry = join(rootDirectory, 'src/features/mermaid/renderer/entry.ts'),
  scriptFiles = [
    fileURLToPath(import.meta.url),
    fileURLToPath(new URL('./mermaid-renderer-cache.mjs', import.meta.url))
  ],
  buildOptions = rendererBuildOptions(entry),
  nodeVersion = process.version,
  buildOperation = generateRenderer,
  dev = false,
  force = false,
  signal,
  log = console.log
} = {}) {
  return prepareCachedRenderer({
    rootDirectory,
    outputDirectory,
    entry,
    scriptFiles,
    buildOptions,
    nodeVersion,
    buildOperation,
    dev,
    force,
    signal,
    log
  })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  if (args.some((arg) => !['--dev', '--force'].includes(arg)))
    throw new Error('Usage: build-mermaid-renderer.mjs [--dev] [--force]')
  await prepareRenderer({ dev: args.includes('--dev'), force: args.includes('--force') })
}
