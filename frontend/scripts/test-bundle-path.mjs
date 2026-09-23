import assert from 'node:assert/strict'
import { posix, win32 } from 'node:path'
import test from 'node:test'
import { resolveBundlePath } from './bundle-path.mjs'

for (const [platform, pathApi, directory] of [
  ['Windows', win32, 'D:\\aw-center-ultra\\frontend\\dist'],
  ['POSIX', posix, '/aw-center/frontend/dist']
]) {
  test(`${platform}: resolves bundle URLs within dist with or without a trailing separator`, () => {
    for (const dist of [directory, directory + pathApi.sep]) {
      assert.equal(
        resolveBundlePath(dist, 'assets/index-B4z4P3pI.js', pathApi),
        pathApi.join(directory, 'assets', 'index-B4z4P3pI.js')
      )
    }
  })

  test(`${platform}: rejects paths outside dist and dist itself`, () => {
    for (const reference of [
      '.',
      '..',
      '../outside.js',
      '../dist-other/index.js',
      'assets/../../outside.js',
      pathApi.resolve(directory, '../outside.js')
    ]) {
      assert.throws(
        () => resolveBundlePath(directory, reference, pathApi),
        /Unsafe initial JavaScript path/
      )
    }
  })
}

test('Windows: rejects backslash traversal, other drives and UNC paths', () => {
  for (const reference of [
    'assets\\..\\..\\outside.js',
    'E:\\outside.js',
    '\\\\server\\share\\outside.js'
  ]) {
    assert.throws(
      () => resolveBundlePath('D:\\frontend\\dist', reference, win32),
      /Unsafe initial JavaScript path/
    )
  }
})
