import { build } from 'vite'
import { fileURLToPath } from 'node:url'
import { mkdir, rename, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { join, resolve } from 'node:path'

const outputDirectory = fileURLToPath(new URL('../.cache/mermaid/', import.meta.url))
/** Concurrent dev/test/build readers always observe a complete old or new bundle. */
export async function publishRenderer(source, directory) {
  await mkdir(directory, { recursive: true })
  const temporary = join(directory, `renderer-${randomUUID()}.tmp`)
  await writeFile(temporary, source, { flag: 'wx' })
  await rename(temporary, join(directory, 'renderer.js'))
}

async function buildRenderer() {
  const result = await build({
    configFile: false,
    publicDir: false,
    logLevel: 'warn',
    build: {
      write: false,
      target: 'es2024',
      lib: {
        entry: fileURLToPath(new URL('../src/features/mermaid/renderer/entry.ts', import.meta.url)),
        name: 'AWMermaidRenderer',
        formats: ['iife'],
        fileName: () => 'renderer.js'
      },
      rolldownOptions: { output: { codeSplitting: false } }
    }
  })
  const output = (Array.isArray(result) ? result : [result]).flatMap((bundle) => bundle.output)
  if (output.length !== 1 || output[0].type !== 'chunk' || /\bimport\s*\(/.test(output[0].code))
    throw new Error('Mermaid renderer must be a single self-contained classic script.')
  await publishRenderer(output[0].code, outputDirectory)
  console.log('Isolated Mermaid renderer built with no runtime imports.')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  await buildRenderer()
