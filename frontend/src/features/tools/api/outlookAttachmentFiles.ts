import { apiClient as axios } from '@/shared/api/http'
import {
  loadOutlookPdfAttachments as loadPdfAttachments,
  validateOutlookDownloadCapability,
  validatePdfBlob,
  type OutlookAttachmentDescriptor,
  type OutlookPdfLoadResult
} from '@/features/tools/api/outlookAttachmentPolicy'

export {
  isPdfAttachment,
  selectOutlookPdfInputs,
  validateOutlookDownloadCapability,
  validatePdfBlob,
  type OutlookPdfFailure,
  type OutlookPdfLoadResult
} from '@/features/tools/api/outlookAttachmentPolicy'

type AttachmentDownloader = (attachment: OutlookAttachmentDescriptor) => Promise<File>

/** Download every PDF attachment sequentially to keep browser memory bounded. */
export async function loadOutlookPdfAttachments(
  attachments: OutlookAttachmentDescriptor[],
  downloader: AttachmentDownloader = downloadOutlookPdfAttachment
): Promise<OutlookPdfLoadResult> {
  return loadPdfAttachments(attachments, downloader)
}

/** Download and verify one owner-bound Outlook PDF attachment. */
export async function downloadOutlookPdfAttachment(
  attachment: OutlookAttachmentDescriptor
): Promise<File> {
  const blob = await downloadOutlookAttachmentBlob(attachment)
  await validatePdfBlob(blob, attachment.size)
  return new File([blob], attachment.name, { type: 'application/pdf' })
}

/** Download one private same-origin Outlook attachment. */
export async function downloadOutlookAttachmentBlob(
  attachment: OutlookAttachmentDescriptor
): Promise<Blob> {
  const capability = validateOutlookDownloadCapability(attachment.download_capability)
  return (
    await axios.post<Blob>('tools/outlook/msg/download/', { capability }, { responseType: 'blob' })
  ).data
}
