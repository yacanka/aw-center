import axios from 'axios'

export interface MediaConversionParameters {
  output_extension: string
  width?: number | null
  height?: number | null
  video_bitrate_kbps?: number | null
  audio_bitrate_kbps?: number | null
}

export interface MediaPreviewResult {
  estimated_bytes: number
  duration_seconds: number | null
  method: string
}

/** Requests an estimated media output size before conversion starts. */
export async function previewMediaConversion(
  file: File,
  parameters: MediaConversionParameters
): Promise<MediaPreviewResult> {
  const response = await axios.post<MediaPreviewResult>(
    '/media-tools/preview/',
    createMediaFormData(file, parameters)
  )
  return response.data
}

/** Converts uploaded media and returns a downloadable Blob response. */
export async function convertMedia(
  file: File,
  parameters: MediaConversionParameters
): Promise<Blob> {
  const response = await axios.post(
    '/media-tools/convert/',
    createMediaFormData(file, parameters),
    {
      responseType: 'blob'
    }
  )
  return response.data
}

function createMediaFormData(file: File, parameters: MediaConversionParameters): FormData {
  const formData = new FormData()
  formData.append('file', file)
  Object.entries(parameters).forEach(([key, value]) => appendValue(formData, key, value))
  return formData
}

function appendValue(formData: FormData, key: string, value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return

  formData.append(key, String(value))
}
