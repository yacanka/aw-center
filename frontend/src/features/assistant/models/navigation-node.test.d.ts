// The browser project intentionally has no Node type dependency. This test-only
// declaration covers the filesystem operation used by the canonical guide contract.
declare module 'node:fs' {
  export function readFileSync(path: URL, encoding: 'utf8'): string
}
