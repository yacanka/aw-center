import { gzipSync } from 'node:zlib'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ASSET_DIRECTORY = fileURLToPath(new URL('../dist/assets/', import.meta.url))
const MAX_RAW_BYTES = 950 * 1024
const MAX_GZIP_BYTES = 250 * 1024

function findNaiveUiBundle() {
  const fileName = readdirSync(ASSET_DIRECTORY).find(
    (candidate) => candidate.startsWith('vendor-naive-ui-') && candidate.endsWith('.js')
  )

  if (!fileName) throw new Error('Naive UI bundle was not found in dist/assets')
  return join(ASSET_DIRECTORY, fileName)
}

function assertWithinBudget(label, actualBytes, maximumBytes) {
  if (actualBytes <= maximumBytes) return

  throw new Error(`${label} is ${actualBytes} bytes; budget is ${maximumBytes} bytes`)
}

const bundle = readFileSync(findNaiveUiBundle())
const gzipBytes = gzipSync(bundle).byteLength

assertWithinBudget('Naive UI raw bundle', bundle.byteLength, MAX_RAW_BYTES)
assertWithinBudget('Naive UI gzip bundle', gzipBytes, MAX_GZIP_BYTES)

console.log(`Naive UI bundle budget passed: ${bundle.byteLength} raw, ${gzipBytes} gzip bytes`)
