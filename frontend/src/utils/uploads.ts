import type { UploadFileInfo } from 'naive-ui'

/** Returns the first browser file or reports a stale/invalid upload selection. */
export function selectedUploadFile(fileList: UploadFileInfo[]): File | null {
  const file = fileList[0]?.file
  if (file instanceof File) return file

  window.$message.error('Select a valid file and try again.')
  return null
}
