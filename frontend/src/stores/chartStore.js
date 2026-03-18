//////// Chart.js ////////
import { getDaysDifference, parseDateFlex, getTodayEUFormat, findPreviousDate } from '@/utils/time'
import 'chartjs-adapter-date-fns'
import { parse } from 'date-fns'
import { useUserStore } from './user'


const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS

export function calculateBarChart(compdocs) {
    let counter = {
        'authority': 0,
        'ubm': 0,
        'aw': 0,
    }

    for (let i = 0; i < compdocs.length; i++) {
        const statusFlowLength = compdocs[i].status_flow.length
        for (let j = 0; j < statusFlowLength; j++) {
            const flow = compdocs[i].status_flow[j]
            let diff
            if (j != statusFlowLength - 1) {
                diff = getDaysDifference(compdocs[i].status_flow[j + 1].date, flow.date)
            } else {
                diff = getDaysDifference(new Date().toISOString().slice(0, 10), flow.date)
            }

            const absDiff = Math.abs(diff)
            if (flow.status == "to_be_updated" || (SHOW_DELAYED_COMPDOCS ? flow.status == "delayed" : (statusFlowLength == 1 && flow.status == "to_be_issued" && diff > 0))) {
                counter["ubm"] += absDiff
            } else if (flow.status == "airworthiness_review" || flow.status == "to_be_re-submitted") {
                counter["aw"] += absDiff
            } else if (flow.status == "authority_review") {
                counter["authority"] += absDiff
            }
        }
    }

    return counter
}

export function calculatePieChart(compdocs) {
    let counter = {
        'delayed': 0,
        'to_be_issued': 0,
        'airworthiness_review': 0,
        'to_be_re-submitted': 0,
        'to_be_updated': 0,
        'authority_review': 0,
        'authority_approved': 0,
    }

    compdocs.forEach((compdoc) => {
        if (SHOW_DELAYED_COMPDOCS) {
            counter[compdoc.status]++
        } else {
            if (compdoc.status_flow.length == 1 && compdoc.status_flow[0].status == "to_be_issued" && (getDaysDifference(getTodayEUFormat(), compdoc?.ubm_target_date) || 0) > 0) {
                counter["delayed"]++
            } else {
                counter[compdoc.status]++
            }
        }
    })
    return counter
}

export function calculateLineChart(compdocs) {
    const sortByDate = (dateObj1, dateObj2) => {
        const date1 = parseDateFlex(dateObj1.x);
        const date2 = parseDateFlex(dateObj2.x);

        return date1 - date2;
    }
    let counterScheduled = {}
    let counterActual = {}

    compdocs.forEach((compdoc) => {
        const firstItem = compdoc.status_flow[0] || null
        const secondItem = compdoc.status_flow[1] || null

        if (firstItem && (firstItem.status == "to_be_issued" || firstItem.status == "delayed")) {
            counterScheduled[firstItem.date] = counterScheduled[firstItem.date] + 1 || 1
        }

        if (secondItem) {
            counterActual[secondItem.date] = counterActual[secondItem.date] + 1 || 1
        }
    })

    let scheduled = Object.entries(counterScheduled).map(([key, value]) => ({ x: key, y: value })).sort(sortByDate);
    let actual = Object.entries(counterActual).map(([key, value]) => ({ x: key, y: value })).sort(sortByDate);

    let total
    total = window.$compdocStore.getCompdocs.length
    scheduled = scheduled.map((item) => {
        total -= item.y
        return { x: item.x, y: total }
    })

    total = window.$compdocStore.getCompdocs.length
    actual = actual.map((item) => {
        total -= item.y
        return { x: item.x, y: total }
    })

    const today = { x: getTodayEUFormat(), y: actual.length > 0 ? actual[actual.length - 1].y : 0 }

    if (actual.length > 0 && actual[actual.length - 1].x != today) {
        actual.push(today)
    }

    const scheduledDatesArray = scheduled.map((item) => item.x)
    const actualDatesArray = actual.map((item) => item.x)

    const scheduledClosestIndex = findPreviousDate(scheduledDatesArray, today.x)
    const actualClosestIndex = findPreviousDate(actualDatesArray, today.x)

    let result = {
        scheduled: scheduled,
        actual: actual,
        today: [today],
        lastScheduled: { x: scheduled[scheduledClosestIndex]?.x, y: scheduled[scheduledClosestIndex]?.y },
        lastActual: { x: actual[actualClosestIndex]?.x, y: actual[actualClosestIndex]?.y }
    }

    return result
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
        },
        outlabels: {
            text: () => null
        }
    }
}

export function getPieChartOptionsLabel() {
    const pieChartOptionsLabel = {
        responsive: false,
        maintainAspectRatio: false,
        aspectRatio: 1,
        radius: '65%',
        layout: {
            padding: { right: 50 },
        },
        plugins: {
            legend: {
                display: true,
                position: 'bottom',
                labels: {
                    boxWidth: 10,
                    usePointStyle: true
                },
            },
            title: {
                display: true,
                text: 'Documents Status'
            },
            tooltip: {
                callbacks: {
                    label: () => null
                }
            },
            outlabels: {
                text: (ctx) => {
                    const value = ctx.chart.data.datasets[0].data[ctx.dataIndex]
                    return (value == 0 ? null : '%p %l (%v)')
                },
                color: window.$userStore?.getPreferences.theme == 'dark' ? '#fff' : '#333639',
                //color: useUserStore().getPreferences.theme == 'dark' ? '#fff' : '#333639',
                //backgroundColor: '#333',
                //borderColor: '#000',
                borderWidth: 2,
                borderRadius: 6,
                padding: { top: -4 },
                //lineColor: '#fff',
                lineWidth: 2,
                stretch: 12,
                font: {
                    resizable: true,
                    minSize: 8,
                    maxSize: 12,
                    weight: 'bold',
                    lineHeight: 1.1
                },
                textAlign: 'center',
            }
        }
    }
    return pieChartOptionsLabel
}

export function getLineChartOptions(annotationX = null, annotationY = null) {
    const lineChartOptions = {
        responsive: false,
        maintainAspectRatio: false,
        plugins: {
            title: {
                display: true,
                text: 'Scheduled and Actual Date'
            },
        },
        scales: {
            y: {
                beginAtZero: true,
                title: {
                    display: true,
                    text: "Remaining"
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
                    text: "Days"
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
                    size: 12,
                },
            },
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
                    size: 12,
                },
            },
        }
    }
    return lineChartOptions
}


export const barChartOptions = JSON.parse(JSON.stringify(pieChartOptions))
barChartOptions.plugins.legend.display = false
barChartOptions.plugins.title.text = "Document Pending Days"
barChartOptions.plugins.tooltip.callbacks.label = chartViewPercentage

const pieChartOptionsPercentage = JSON.parse(JSON.stringify(getPieChartOptionsLabel()))
pieChartOptionsPercentage.plugins.outlabels.text = (ctx) => {
    const value = ctx.chart.data.datasets[0].data[ctx.dataIndex]
    return (value == 0 ? null : '%l (%p)')
}