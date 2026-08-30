import type { UploadFileInfo } from 'naive-ui'

/** Return the first browser file and optionally report a stale selection. */
export function selectedUploadFile(fileList: UploadFileInfo[], reportInvalid = true): File | null {
  const file = fileList[0]?.file
  if (file instanceof File) return file

  if (reportInvalid) window.$message.error('Select a valid file and try again.')
  return null
}
