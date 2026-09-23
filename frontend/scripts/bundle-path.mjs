import path from 'node:path'

export function resolveBundlePath(distDirectory, relativePath, pathApi = path) {
  const bundlePath = pathApi.resolve(distDirectory, relativePath)
  const relative = pathApi.relative(distDirectory, bundlePath)
  if (
    !relative ||
    relative === '..' ||
    relative.startsWith(`..${pathApi.sep}`) ||
    pathApi.isAbsolute(relative)
  ) {
    throw new Error(`Unsafe initial JavaScript path: ${relativePath}`)
  }
  return bundlePath
}
