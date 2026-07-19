import type { FilterOptionValue } from 'naive-ui/es/data-table/src/interface'

type TableRow = object
type FilterValue = FilterOptionValue | FilterOptionValue[]
type DateOperator = '==' | '!=' | '>' | '>=' | '<' | '<='

const DAY_MILLISECONDS = 86_400_000

/** Build a safe substring filter for one table attribute. */
export function getStringFilterFunc(attribute: string) {
  return (value: FilterOptionValue, row: TableRow): boolean => {
    const candidate = readAttribute(row, attribute)
    if (candidate === null || candidate === undefined) return false
    return String(candidate).includes(String(value))
  }
}

/** Build a strict boolean filter for one table attribute. */
export function getBooleanFilterFunc(attribute: string) {
  return (value: FilterOptionValue, row: TableRow): boolean =>
    readAttribute(row, attribute) === value
}

/** Build an intersection filter for array or string-valued attributes. */
export function getArrayFilterFunc(attribute: string) {
  return (value: FilterValue, row: TableRow): boolean => {
    const selected = Array.isArray(value) ? value : [value]
    if (!selected.length) return true
    return selected.some((item) => containsValue(readAttribute(row, attribute), item))
  }
}

/** Build a resilient date-comparison filter for one table attribute. */
export function getDateFilterFunc(attribute: string) {
  return (value: FilterOptionValue, row: TableRow): boolean => {
    const filter = value as unknown as { date?: string; type?: DateOperator }
    if (!filter.date || !filter.type) return true
    const difference = differenceInDays(readAttribute(row, attribute), filter.date)
    return difference === null ? false : compareDifference(difference, filter.type)
  }
}

function containsValue(candidate: unknown, selected: FilterOptionValue): boolean {
  if (Array.isArray(candidate)) return candidate.some((item) => item === selected)
  if (candidate === null || candidate === undefined) return false
  return String(candidate).includes(String(selected))
}

function readAttribute(row: TableRow, attribute: string): unknown {
  return Reflect.get(row, attribute)
}

function differenceInDays(left: unknown, right: string): number | null {
  const leftTime = parseDate(left)
  const rightTime = parseDate(right)
  if (leftTime === null || rightTime === null) return null
  return Math.trunc((leftTime - rightTime) / DAY_MILLISECONDS)
}

function parseDate(value: unknown): number | null {
  if (typeof value !== 'string') return null
  const parts = dateParts(value.trim())
  if (!parts) return null
  const [year, month, day] = parts
  const timestamp = Date.UTC(year, month - 1, day)
  const date = new Date(timestamp)
  return isSameDate(date, year, month, day) ? timestamp : null
}

function dateParts(value: string): [number, number, number] | null {
  const european = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value)
  if (european) return [Number(european[3]), Number(european[2]), Number(european[1])]
  const iso = /^(\d{4})[-/](\d{2})[-/](\d{2})$/.exec(value)
  return iso ? [Number(iso[1]), Number(iso[2]), Number(iso[3])] : null
}

function isSameDate(date: Date, year: number, month: number, day: number): boolean {
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  )
}

function compareDifference(difference: number, operator: DateOperator): boolean {
  if (operator === '==') return difference === 0
  if (operator === '!=') return difference !== 0
  if (operator === '>') return difference > 0
  if (operator === '>=') return difference >= 0
  if (operator === '<') return difference < 0
  return difference <= 0
}
