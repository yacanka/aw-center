import { gzipSync } from 'node:zlib'
import { readFileSync } from 'node:fs'
import { basename, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const DIST_DIRECTORY = fileURLToPath(new URL('../dist/', import.meta.url))
const MAX_LOGIN_INITIAL_GZIP_BYTES = 300 * 1024
const FORBIDDEN_LOGIN_CHUNKS = /(?:chart|markdown|date-fns)/i

function assertWithinBudget(label, actualBytes, maximumBytes) {
  if (actualBytes <= maximumBytes) return

  throw new Error(`${label} is ${actualBytes} bytes; budget is ${maximumBytes} bytes`)
}

const initialBundles = findInitialJavaScriptBundles()
const forbiddenInitialBundles = initialBundles.filter((path) =>
  FORBIDDEN_LOGIN_CHUNKS.test(basename(path))
)
const initialGzipBytes = initialBundles.reduce(
  (total, path) => total + gzipSync(readFileSync(path)).byteLength,
  0
)

assertWithinBudget(
  'Login initial JavaScript gzip total',
  initialGzipBytes,
  MAX_LOGIN_INITIAL_GZIP_BYTES
)
if (forbiddenInitialBundles.length > 0) {
  throw new Error(
    `Login initial graph contains feature-heavy chunks: ${forbiddenInitialBundles
      .map((path) => basename(path))
      .join(', ')}`
  )
}

console.log(
  `Login initial JavaScript budget passed: ${initialGzipBytes} gzip bytes across ${initialBundles.length} files`
)

function findInitialJavaScriptBundles() {
  const index = readFileSync(join(DIST_DIRECTORY, 'index.html'), 'utf8')
  const references = [...index.matchAll(/(?:src|href)="([^"]+\.js(?:\?[^\"]*)?)"/g)].map(
    (match) => match[1]
  )
  const paths = references.map((reference) => {
    const pathname = new URL(reference, 'https://awcenter.invalid').pathname
    const assetsOffset = pathname.indexOf('/assets/')
    if (assetsOffset < 0) throw new Error(`Unexpected initial JavaScript path: ${reference}`)
    const relativePath = pathname.slice(assetsOffset + 1)
    const path = resolve(DIST_DIRECTORY, relativePath)
    if (!path.startsWith(`${resolve(DIST_DIRECTORY)}/`)) {
      throw new Error(`Unsafe initial JavaScript path: ${reference}`)
    }
    return path
  })
  return [...new Set(paths)]
}
