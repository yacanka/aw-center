import 'chartjs-adapter-date-fns'
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  DoughnutController,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  TimeScale,
  Tooltip,
  type Chart,
  type ChartOptions,
  type Plugin,
  type TooltipItem
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import type { ThemeName } from '@/services/theme'

let registered = false
const COMPDOC_REGISTERABLES = [
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  DoughnutController,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  TimeScale,
  Tooltip,
  annotationPlugin
]

/** Register only modern Chart.js primitives used by CompDoc visualizations. */
export function ensureCompdocChartsRegistered() {
  if (registered) return
  ChartJS.register(...COMPDOC_REGISTERABLES)
  registered = true
}

export const centerTextPlugin: Plugin<'doughnut'> = {
  id: 'compdocCenterText',
  afterDatasetsDraw: drawCenterText
}

/** Return responsive doughnut options with useful count and percentage tooltips. */
export function createStatusChartOptions(theme: ThemeName): ChartOptions<'doughnut'> {
  const colors = getCompdocChartColors(theme)
  return {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '68%',
    color: colors.text,
    animation: { duration: 500 },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: colors.tooltip,
        padding: 12,
        displayColors: true,
        callbacks: { label: percentageTooltip }
      }
    }
  }
}

function percentageTooltip(context: TooltipItem<'doughnut'>) {
  const total = context.dataset.data.reduce((sum, value) => sum + Number(value || 0), 0)
  const value = Number(context.raw || 0)
  const percentage = total ? Math.round((value / total) * 100) : 0
  return ` ${context.label}: ${value} (${percentage}%)`
}

function drawCenterText(chart: Chart<'doughnut'>) {
  const values = chart.data.datasets[0]?.data || []
  const total = values.reduce((sum, value) => sum + Number(value || 0), 0)
  if (!chart.chartArea) return
  const centerX = (chart.chartArea.left + chart.chartArea.right) / 2
  const centerY = chart.chartArea.top + chart.chartArea.height / 2
  const color = String(chart.options.color || '#334155')
  chart.ctx.save()
  drawLabel(chart.ctx, String(total), centerX, centerY - 8, color, '700 28px')
  chart.ctx.globalAlpha = 0.72
  drawLabel(chart.ctx, 'DOCUMENTS', centerX, centerY + 18, color, '500 11px')
  chart.ctx.restore()
}

function drawLabel(
  context: CanvasRenderingContext2D,
  label: string,
  x: number,
  y: number,
  color: string,
  font: string
) {
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillStyle = color
  context.font = `${font} Inter, system-ui, sans-serif`
  context.fillText(label, x, y)
}

/** Return semantic colors shared by CompDoc chart options. */
export function getCompdocChartColors(theme: ThemeName) {
  const dark = theme === 'dark'
  return {
    text: dark ? '#e5e7eb' : '#1f2937',
    muted: dark ? '#9ca3af' : '#64748b',
    grid: dark ? 'rgba(148, 163, 184, 0.18)' : 'rgba(100, 116, 139, 0.16)',
    tooltip: dark ? 'rgba(15, 23, 42, 0.96)' : 'rgba(30, 41, 59, 0.96)'
  }
}
