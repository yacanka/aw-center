import axios from 'axios'

/** Inspect the first worksheet's column contract without retaining the file. */
export async function inspectExcelColumns(file: File): Promise<string[]> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await axios.post<string[]>('/excel/get_excel_columns/', formData)
  return response.data
}
