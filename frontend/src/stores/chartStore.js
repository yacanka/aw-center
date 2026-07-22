//////// Chart.js ////////
import 'chartjs-adapter-date-fns'
import { parse } from 'date-fns'

import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  TimeScale,
  Title,
  Tooltip
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'

let areChartPluginsRegistered = false

/**
 * Ensures Chart.js elements and plugins are registered once before chart rendering.
 */
export function ensureChartPluginsRegistered() {
  if (areChartPluginsRegistered) return

  ChartJS.register(
    Title,
    Tooltip,
    Legend,
    BarElement,
    CategoryScale,
    LinearScale,
    ArcElement,
    PointElement,
    LineElement,
    TimeScale,
    annotationPlugin
  )

  areChartPluginsRegistered = true
}

const chartViewPercentage = (context) => {
  const meta = context.chart.getDatasetMeta(0)
  const dataset = context.dataset.data

  const visibleData = dataset.filter((_, i) => !context.chart._hiddenIndices?.[i])
  const visibleTotal = visibleData.reduce((a, b) => a + b, 0)
  const value = context.raw

  const percentage = ((value / visibleTotal) * 100).toFixed(1)
  return `${value} (%${percentage})`
}

export const pieChartOptions = {
  responsive: false,
  maintainAspectRatio: false,
  aspectRatio: 1,
  plugins: {
    legend: {
      display: true,
      position: 'right',
      labels: {
        boxWidth: 20,
        usePointStyle: true
      },
      align: 'center'
    },
    title: {
      display: true,
      text: 'Documents Status'
    },
    tooltip: {
      callbacks: {
        label: chartViewPercentage
      }
    }
  }
}

/**
 * Builds line-chart options with optional reference annotations.
 *
 * @param {string | number | null} [annotationX]
 * @param {number | null} [annotationY]
 */
export function getLineChartOptions(annotationX = null, annotationY = null) {
  const lineChartOptions = {
    responsive: false,
    maintainAspectRatio: false,
    plugins: {
      title: {
        display: true,
        text: 'Scheduled and Actual Date'
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'Remaining'
        }
      },
      x: {
        type: 'time',
        time: {
          unit: 'day',
          parser: (dateString) => parse(dateString, 'dd.MM.yyyy', new Date()),
          tooltipFormat: 'dd.MM.yyyy',
          displayFormats: {
            day: 'dd.MM.yyyy'
          }
        },
        //min: '01.01.2024',
        //max: '01.01.2027',
        bounds: 'data',
        //ticks: {source: 'data'},
        title: {
          display: true,
          text: 'Days'
        }
      }
    }
  }
  if (annotationX || annotationY) {
    lineChartOptions.plugins.annotation = {
      annotations: {}
    }
  }
  if (annotationX) {
    lineChartOptions.plugins.annotation.annotations.vertical = {
      type: 'line',
      xMin: annotationX,
      xMax: annotationX,
      borderColor: 'rgba(128, 128, 128, 0.50)',
      borderWidth: 2,
      borderDash: [3, 3],
      label: {
        content: annotationX,
        display: true,
        position: 'end',
        backgroundColor: 'rgba(128, 128, 128, 0.70)',
        color: 'white',
        font: {
          size: 12
        }
      }
    }
  }
  if (annotationY) {
    lineChartOptions.plugins.annotation.annotations.horizontal = {
      type: 'line',
      yMin: annotationY,
      yMax: annotationY,
      borderColor: 'rgba(255, 165, 0, 0.50)',
      borderWidth: 1,
      borderDash: [4, 4],
      label: {
        content: annotationY,
        display: true,
        position: 'end',
        backgroundColor: 'rgba(255, 165, 0, 0.70)',
        color: 'white',
        font: {
          size: 12
        }
      }
    }
  }
  return lineChartOptions
}

export const barChartOptions = JSON.parse(JSON.stringify(pieChartOptions))
barChartOptions.plugins.legend.display = false
barChartOptions.plugins.title.text = 'Document Pending Days'
barChartOptions.plugins.tooltip.callbacks.label = chartViewPercentage
