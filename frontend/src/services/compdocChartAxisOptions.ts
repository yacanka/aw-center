import type { ChartOptions } from 'chart.js'
import type { ThemeName } from '@/services/theme'
import { toIsoDate } from '@/services/compdocChartData'
import { getCompdocChartColors } from '@/services/compdocChartTheme'

/** Return readable time-axis options for stepped scheduled/actual burndown lines. */
export function createTimelineChartOptions(
  theme: ThemeName,
  today: string | undefined,
  documentCount: number
): ChartOptions<'line'> {
  const colors = getCompdocChartColors(theme)
  return {
    responsive: true,
    maintainAspectRatio: false,
    locale: 'tr-TR',
    color: colors.text,
    interaction: { mode: 'nearest', intersect: false, axis: 'x' },
    animation: { duration: 450 },
    plugins: timelinePlugins(colors, today),
    scales: timelineScales(colors, documentCount)
  }
}

/** Return compact horizontal pending-day bar options. */
export function createPendingChartOptions(theme: ThemeName): ChartOptions<'bar'> {
  const colors = getCompdocChartColors(theme)
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    color: colors.text,
    plugins: pendingPlugins(colors),
    scales: pendingScales(colors)
  }
}

type ChartColors = ReturnType<typeof getCompdocChartColors>

function timelinePlugins(colors: ChartColors, today: string | undefined) {
  const annotationDate = today ? toIsoDate(today) : null
  return {
    legend: { position: 'top' as const, align: 'end' as const, labels: legendLabels() },
    tooltip: { backgroundColor: colors.tooltip, padding: 12 },
    annotation: annotationDate ? todayAnnotation(annotationDate) : undefined
  }
}

function timelineScales(colors: ChartColors, documentCount: number) {
  return {
    x: timeScale(colors),
    y: remainingScale(colors, documentCount)
  }
}

function timeScale(colors: ChartColors) {
  return {
    type: 'time' as const,
    time: {
      unit: 'day' as const,
      tooltipFormat: 'dd MMMM yyyy',
      displayFormats: { day: 'dd MMM' }
    },
    grid: { display: false },
    ticks: { color: colors.muted, maxTicksLimit: 8, maxRotation: 0 },
    border: { color: colors.grid }
  }
}

function remainingScale(colors: ChartColors, documentCount: number) {
  return {
    beginAtZero: true,
    suggestedMax: Math.max(documentCount, 1),
    ticks: { color: colors.muted, precision: 0 },
    grid: { color: colors.grid },
    border: { display: false },
    title: { display: true, text: 'Remaining documents', color: colors.muted }
  }
}

function pendingPlugins(colors: ChartColors) {
  return {
    legend: { display: false },
    tooltip: { backgroundColor: colors.tooltip, padding: 12 }
  }
}

function pendingScales(colors: ChartColors) {
  return {
    x: {
      beginAtZero: true,
      ticks: { color: colors.muted, precision: 0 },
      grid: { color: colors.grid },
      border: { display: false },
      title: { display: true, text: 'Days', color: colors.muted }
    },
    y: { grid: { display: false }, ticks: { color: colors.text }, border: { display: false } }
  }
}

function legendLabels() {
  return { usePointStyle: true, boxWidth: 8 }
}

function todayAnnotation(date: string) {
  return {
    annotations: {
      today: {
        type: 'line' as const,
        xMin: date,
        xMax: date,
        borderColor: '#ef4444',
        borderWidth: 2,
        borderDash: [5, 5],
        label: todayLabel()
      }
    }
  }
}

function todayLabel() {
  return {
    display: true,
    content: 'Today',
    position: 'start' as const,
    color: '#ffffff',
    backgroundColor: '#ef4444',
    padding: 5
  }
}
