const fs = require('fs')
const path = require('path')

const frontendDistDirectory = path.resolve(__dirname, '../dist')
const frontendIndexFile = path.join(frontendDistDirectory, 'index.html')
const frontendAssetsDirectory = path.join(frontendDistDirectory, 'assets')

function assertPathExists(filePath, description) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`${description} was not generated: ${filePath}`)
  }
}

function summarizeBuildOutput() {
  assertPathExists(frontendIndexFile, 'Frontend entry file')
  assertPathExists(frontendAssetsDirectory, 'Frontend assets directory')

  const html = fs.readFileSync(frontendIndexFile, 'utf8')
  for (const [rel, href] of [
    ['manifest', '/app/manifest.webmanifest'],
    ['icon', '/app/icons/pwa-192.png'],
    ['apple-touch-icon', '/app/icons/pwa-192.png']
  ]) {
    if (!html.includes(`rel="${rel}" href="${href}"`)) {
      throw new Error(`Frontend ${rel} must use the Django URL ${href}`)
    }
    assertPathExists(path.join(frontendDistDirectory, href.slice(1)), `Frontend ${rel}`)
  }

  console.log('Frontend build verified for Django serving from frontend/dist.')
}

summarizeBuildOutput()
