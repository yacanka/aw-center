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

  console.log('Frontend build verified for Django serving from frontend/dist.')
}

summarizeBuildOutput()
