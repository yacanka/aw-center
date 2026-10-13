type DateValue = string | Date | number | null | undefined

const dateOptions: Intl.DateTimeFormatOptions = {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: 'Europe/Istanbul'
}

function calendarDate(value: string): Date | null {
  const iso = /^(\d{4})[-/](\d{2})[-/](\d{2})$/.exec(value)
  const turkish = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value)
  if (!iso && !turkish) return null
  const [year, month, day] = iso
    ? [Number(iso[1]), Number(iso[2]), Number(iso[3])]
    : [Number(turkish![3]), Number(turkish![2]), Number(turkish![1])]
  const date = new Date(0)
  date.setUTCFullYear(year, month - 1, day)
  return date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
    ? date
    : new Date(NaN)
}

function instant(value: DateValue): Date {
  if (value == null || value === '') return new Date(NaN)
  // Legacy timezone-less timestamps represent Turkish time, not the browser's zone.
  if (
    typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value)
  ) {
    return new Date(`${value.replace(' ', 'T')}+03:00`)
  }
  return value instanceof Date ? value : new Date(value)
}

/** Display calendar dates unchanged; display timestamp dates in Europe/Istanbul. */
export function formatTurkishDate(value: DateValue): string {
  const calendar = typeof value === 'string' ? calendarDate(value) : null
  const date = calendar ?? instant(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('tr-TR', {
    ...dateOptions,
    ...(calendar ? { timeZone: 'UTC' } : {})
  }).format(date)
}

/** Display an instant using the project's Turkish 24-hour clock. */
export function formatTurkishDateTime(value: DateValue, includeSeconds = false): string {
  const date = instant(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('tr-TR', {
    ...dateOptions,
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
    hourCycle: 'h23'
  }).format(date)
}

export function formatTurkishTime(value: DateValue, includeSeconds = true): string {
  const date = instant(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('tr-TR', {
    timeZone: 'Europe/Istanbul',
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
    hourCycle: 'h23'
  }).format(date)
}

export function isoToTurkishDateTime(isoDate: string) {
  return formatTurkishDateTime(isoDate, true)
}

export function getDaysDifference(dateStr1: string, dateStr2: string) {
  const date1 = parseDateFlex(dateStr1)
  const date2 = parseDateFlex(dateStr2)

  if (isNaN(date1.getTime()) || isNaN(date2.getTime())) {
    return null
  }

  const diffMs = date1.getTime() - date2.getTime()

  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  return diffDays
}

export function parseDateFlex(strDate: string) {
  strDate = strDate?.trim()

  if (/^\d{2}\.\d{2}\.\d{4}$/.test(strDate)) {
    const [day, month, year] = strDate.split('.').map(Number)
    return new Date(year, month - 1, day)
  }

  if (/^\d{4}[-/]\d{2}[-/]\d{2}$/.test(strDate)) {
    return new Date(strDate)
  }

  const d = new Date(strDate)
  if (!isNaN(d.getTime())) return d

  throw new Error('Invalid Date Format: ' + strDate)
}

export function getTodayEUFormat() {
  return formatTurkishDate(new Date())
}

export function sortedDates(dates: any[]) {
  return dates.sort((a, b) => {
    const [ad, am, ay] = a.split('.').map(Number)
    const [bd, bm, by] = b.split('.').map(Number)
    return new Date(ay, am - 1, ad).getTime() - new Date(by, bm - 1, bd).getTime()
  })
}

export function findPreviousDate(datesArray: string[], targetDateStr: string) {
  const targetDate = parseDateFlex(targetDateStr)

  let closestIndex = -1
  let minDiff = Infinity

  datesArray.forEach((dateStr, index) => {
    const date = parseDateFlex(dateStr)

    let diff = date.getTime() - targetDate.getTime()
    if (diff < 0) {
      diff = Math.abs(diff)
      if (diff < minDiff) {
        minDiff = diff
        closestIndex = index // Orijinal stringi döndür
      }
    }
  })

  return closestIndex
}

/** Offset calendar days in Turkey without browser timezone or DST shifts. */
export function dateDaysOffset(offset: number, dateInput?: string) {
  const date = calendarDate(dateInput ? formatTurkishDate(dateInput) : getTodayEUFormat())
  if (!date || Number.isNaN(date.getTime())) throw new Error('Invalid Date Format: ' + dateInput)
  date.setUTCDate(date.getUTCDate() + offset)
  return new Intl.DateTimeFormat('tr-TR', { ...dateOptions, timeZone: 'UTC' }).format(date)
}
