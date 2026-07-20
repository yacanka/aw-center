import axios from 'axios'
import type { IAttachment } from '@/models/outlook'

export interface OutlookPdfFailure {
  name: string
  reason: string
}

export interface OutlookPdfLoadResult {
  files: File[]
  failures: OutlookPdfFailure[]
}

type AttachmentDownloader = (attachment: IAttachment) => Promise<File>

/** Download every PDF attachment sequentially to keep browser memory bounded. */
export async function loadOutlookPdfAttachments(
  attachments: IAttachment[],
  downloader: AttachmentDownloader = downloadOutlookPdfAttachment
): Promise<OutlookPdfLoadResult> {
  const result: OutlookPdfLoadResult = { files: [], failures: [] }
  for (const attachment of attachments.filter(isPdfAttachment)) {
    try {
      result.files.push(await downloader(attachment))
    } catch (error) {
      result.failures.push({ name: attachment.name, reason: attachmentError(error) })
    }
  }
  return result
}

/** Prefer manually supplied files over stale MSG attachments with the same name. */
export function selectOutlookPdfInputs(
  loaded: OutlookPdfLoadResult,
  manualFiles: File[]
): OutlookPdfLoadResult {
  const manualNames = new Set(manualFiles.map((file) => normalizedName(file.name)))
  const automatic = loaded.files.filter((file) => !manualNames.has(normalizedName(file.name)))
  const failures = loaded.failures.filter(
    (failure) => !manualNames.has(normalizedName(failure.name))
  )
  return { files: [...automatic, ...manualFiles], failures }
}

/** Download and verify one owner-bound Outlook PDF attachment. */
export async function downloadOutlookPdfAttachment(attachment: IAttachment): Promise<File> {
  const downloadUrl = validateOutlookDownloadUrl(attachment.download_url)
  const response = await axios.get<Blob>(downloadUrl, { responseType: 'blob' })
  await validatePdfBlob(response.data, attachment.size)
  return new File([response.data], attachment.name, { type: 'application/pdf' })
}

/** Return true only for attachments declared as PDF files by name. */
export function isPdfAttachment(attachment: IAttachment): boolean {
  return attachment.name.toLocaleLowerCase('en-US').endsWith('.pdf')
}

/** Restrict attachment reads to the authenticated same-origin Outlook endpoint. */
export function validateOutlookDownloadUrl(downloadUrl?: string): string {
  if (!downloadUrl) throw new Error('The private attachment link is missing.')
  const parsed = new URL(downloadUrl, 'https://awcenter.invalid')
  const isPrivatePath = parsed.pathname === '/outlook/msg/download/'
  if (parsed.origin !== 'https://awcenter.invalid' || !isPrivatePath) {
    throw new Error('The private attachment link is invalid.')
  }
  return `${parsed.pathname}${parsed.search}`
}

/** Verify attachment length and PDF signature before creating a browser File. */
export async function validatePdfBlob(blob: Blob, expectedSize: number): Promise<void> {
  if (!blob.size || blob.size !== expectedSize) {
    throw new Error('The downloaded attachment failed its size check.')
  }
  const header = new Uint8Array(await blob.slice(0, 5).arrayBuffer())
  if (new TextDecoder().decode(header) !== '%PDF-') {
    throw new Error('The downloaded attachment is not a valid PDF.')
  }
}

function attachmentError(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'The private attachment could not be downloaded.'
}

function normalizedName(name: string): string {
  return name.toLocaleLowerCase('en-US')
}
