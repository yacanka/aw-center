<template>
    <n-flex justify="center">
        <n-h1 class="gradient-text" style="margin: -12px 0 -18px 0">
            <strong> {{ appTitle }} </strong>
        </n-h1>
    </n-flex>

    <n-tabs v-model:value="activeTab" @update:value="handleTabChange">
        <n-tab-pane v-for="(project, index) in projectOptions" :name="project.value" :tab="project.label"
            :disabled="project.disabled">
        </n-tab-pane>
    </n-tabs>

    <n-space horizontal>
        <n-space vertical>
            <n-card style="width: 45vw;">
                <n-scrollbar style="max-height: 240px">
                    <n-data-table ref="table" size="tiny" :loading="compStore.isLoading" striped
                        :columns="panelStatusColumns" :data="panelStatus" :row-key="(row: ICompDoc) => row.id"
                        :row-props="rowPropsAttr" />
                </n-scrollbar>
            </n-card>

            <n-card style="width: 45vw">
                <n-space>
                    <Pie :data="pieChartData" :options="getPieChartOptionsLabel()" :width="480" :height="360"
                        :key="JSON.stringify(pieChartData.datasets)" />
                    <n-space vertical>
                        <n-card>
                            <n-grid cols=12 x-gap="0" y-gap="4" style="width: 240px">
                                <n-gi span=12> Issued </n-gi>
                                <n-gi span=12> <n-divider style="margin: -2px" /> </n-gi>
                                <n-gi span=8> Authority Approved </n-gi>
                                <n-gi span=2> {{ statusCounter["authority_approved"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? ((statusCounter["authority_approved"] /
                                    statusCounter["total"] * 100).toFixed(0)) : 0 }}%) </n-gi>
                                <n-gi span=8> Authority Review </n-gi>
                                <n-gi span=2> {{ statusCounter["authority_review"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? ((statusCounter["authority_review"] /
                                    statusCounter["total"] * 100).toFixed(0)) : 0 }}%) </n-gi>
                                <n-gi span=8> Airworthiness Review </n-gi>
                                <n-gi span=2> {{ statusCounter["airworthiness_review"] +
                                    statusCounter["to_be_re-submitted"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? ((statusCounter["airworthiness_review"] +
                                    statusCounter["to_be_re-submitted"] / statusCounter["total"] * 100).toFixed(0)) : 0
                                    }}%) </n-gi>
                                <n-gi span=8> To Be Updated </n-gi>
                                <n-gi span=2> {{ statusCounter["to_be_updated"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? ((statusCounter["to_be_updated"] /
                                    statusCounter["total"] * 100).toFixed(0)) : 0 }}%) </n-gi>
                                <n-gi span=12> <n-divider style="margin: -2px" /> </n-gi>
                                <n-gi span=8> Total </n-gi>
                                <n-gi span=2> {{ statusCounter['total'] - statusCounter["to_be_issued"] -
                                    statusCounter["delayed"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? (((statusCounter["total"] -
                                    statusCounter["to_be_issued"] - statusCounter["delayed"]) / statusCounter["total"] *
                                    100).toFixed(0)) : 0 }}%) </n-gi>
                            </n-grid>
                        </n-card>
                        <n-card>
                            <n-grid cols=12 x-gap="0" y-gap="4" style="width: 240px">
                                <n-gi span=12> Remaining </n-gi>
                                <n-gi span=12> <n-divider style="margin: -2px" /> </n-gi>
                                <n-gi span=8> Delayed </n-gi>
                                <n-gi span=2> {{ statusCounter["delayed"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? ((statusCounter["delayed"] /
                                    statusCounter["total"] * 100).toFixed(0)) : 0 }}%) </n-gi>
                                <n-gi span=8> To Be Issued </n-gi>
                                <n-gi span=2> {{ statusCounter["to_be_issued"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? ((statusCounter["to_be_issued"] /
                                    statusCounter["total"] * 100).toFixed(0)) : 0 }}%) </n-gi>
                                <n-gi span=12> <n-divider style="margin: -2px" /> </n-gi>
                                <n-gi span=8> Total </n-gi>
                                <n-gi span=2> {{ statusCounter["to_be_issued"] + statusCounter["delayed"] }} </n-gi>
                                <n-gi span=2> ({{ statusCounter["total"] ? (((statusCounter["to_be_issued"] +
                                    statusCounter["delayed"]) / statusCounter["total"] * 100).toFixed(0)) : 0 }}%)
                                </n-gi>
                            </n-grid>
                        </n-card>
                    </n-space>
                </n-space>
            </n-card>
        </n-space>

        <n-space vertical>
            <n-card>
                <Line :data="lineChartData"
                    :options="getLineChartOptions(lineChartData.datasets[0]?.data[0]?.x, lineChartData.datasets[0]?.data[0]?.y)"
                    :width="540" :height="420" :key="JSON.stringify(lineChartData.datasets)" />
            </n-card>
            <n-card>
                Scheduled
                <div v-if="performanceMetrics['scheduled']['percentage']" class="dual-progress">
                    <n-progress :percentage="performanceMetrics['scheduled']['percentage']" :height="20"
                        border-radius="6" :show-indicator="false" color="rgba(0, 255, 0, 0.75)"
                        rail-color="rgba(255, 0, 0, 0.75)" />
                    <div class="dual-progress-overlay">
                        <div v-if="performanceMetrics['scheduled']['filled']" class="seg seg--filled label"
                            :style="{ width: `${performanceMetrics['scheduled']['percentage']}%` }">
                            {{ performanceMetrics['scheduled']['filled'] }}
                        </div>
                        <div v-if="performanceMetrics['scheduled']['empty']" class="seg seg--empty label"
                            :style="{ width: `${100 - performanceMetrics['scheduled']['percentage']}%` }">
                            {{ performanceMetrics['scheduled']['empty'] }}
                        </div>
                    </div>
                </div>

                <n-divider style="margin: 12px 0px 8px 0px;" />

                Actual
                <div v-if="performanceMetrics['actual']['percentage']" class="dual-progress">
                    <n-progress :percentage="performanceMetrics['actual']['percentage']" :height="20" border-radius="6"
                        :show-indicator="false" color="rgba(0, 255, 0, 0.75)" rail-color="rgba(255, 0, 0, 0.75)" />
                    <div class="dual-progress-overlay">
                        <div v-if="performanceMetrics['actual']['filled']" class="seg seg--filled label"
                            :style="{ width: `${performanceMetrics['actual']['percentage']}%` }">
                            {{ performanceMetrics['actual']['filled'] }}
                        </div>
                        <div v-if="performanceMetrics['actual']['empty']" class="seg seg--empty label"
                            :style="{ width: `${100 - performanceMetrics['actual']['percentage']}%` }">
                            {{ performanceMetrics['actual']['empty'] }}
                        </div>
                    </div>
                </div>

                <n-divider style="margin: 12px 0px 8px 0px;" />

                Approved
                <div v-if="performanceMetrics['approved']['percentage']" class="dual-progress">
                    <n-progress :percentage="performanceMetrics['approved']['percentage']" :height="20"
                        border-radius="6" :show-indicator="false" color="rgba(0, 255, 0, 0.75)"
                        rail-color="rgba(255, 0, 0, 0.75)" />
                    <div class="dual-progress-overlay">
                        <div v-if="performanceMetrics['approved']['filled']" class="seg seg--filled label"
                            :style="{ width: `${performanceMetrics['approved']['percentage']}%` }">
                            {{ performanceMetrics['approved']['filled'] }}
                        </div>
                        <div v-if="performanceMetrics['approved']['empty']" class="seg seg--empty label"
                            :style="{ width: `${100 - performanceMetrics['approved']['percentage']}%` }">
                            {{ performanceMetrics['approved']['empty'] }}
                        </div>
                    </div>
                </div>
                <!-- <Bar :data="barChartData" :options="barChartOptions" :width="480" :height="240"
                    :key="JSON.stringify(barChartData.datasets)" /> -->
            </n-card>
        </n-space>
    </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useCompdocStore } from '@/stores/api'
import { Pie, Line } from 'vue-chartjs'
import 'chartjs-adapter-date-fns'
import { statusOptions, statusColors } from '@/stores/datatable'
import { calculateBarChart, calculateLineChart, calculatePieChart, getLineChartOptions, getPieChartOptionsLabel } from '@/stores/chartStore'

const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS
const appTitle = import.meta.env.VITE_APP_TITLE
const compStore = useCompdocStore()

const projectOptions = [
    { label: "Özgür-1", value: "ozgur", disabled: false },
    { label: "Blok 30", value: "blok30", disabled: false },
    { label: "Blok 40/50", value: "blok4050", disabled: true },
    { label: "AESA", value: "aesa", disabled: false },
    { label: "HYS", value: "hys", disabled: false },
    { label: "Piku", value: "piku", disabled: false },
    { label: "Gokbey", value: "gokbey", disabled: true },
    { label: "Havasoj", value: "havasoj", disabled: false }
]

const panelStatusColumns: DataTableColumns<ICompDoc> = [
    {
        title: 'Panels',
        key: 'panel',
        width: 25,
        ellipsis: {
            tooltip: true
        },
    },
    {
        title: 'To Be Issued',
        key: 'to_be_issued',
        width: 15,
        align: "center",
        ellipsis: {
            tooltip: true
        },
        render(row: Record<string, any>) {
            return (row["to_be_issued"] || 0) + (row["delayed"] || 0) || null
        }
    },
    {
        title: 'To Be Updated',
        key: 'to_be_updated',
        width: 15,
        align: "center",
    },
    {
        title: 'To Be Re-Submitted',
        key: 'to_be_re-submitted',
        width: 15,
        align: "center",
    },
    {
        title: 'Airworthiness Review',
        key: 'airworthiness_review',
        width: 15,
        align: "center",
    },
    {
        title: 'Authority Review',
        key: 'authority_review',
        width: 15,
        align: "center",
    },
    {
        title: 'Authority Approved',
        key: 'authority_approved',
        width: 15,
        align: "center",
    },
    {
        title: 'Total',
        key: 'total',
        width: 5,
        align: "center",
        render(row) {
            const total = Object.values(row).reduce((sum, val) => {
                if (typeof val === 'number' && !isNaN(val)) {
                    return sum + val;
                }
                return sum;
            }, 0)
            return total
        }
    },
]

const activeTab = ref()
const panelStatus = ref<any[]>([])

const pieChartData = ref({
    labels: statusOptions.map(item => item.label),
    datasets: [
        {
            data: [],
            backgroundColor: statusOptions.map(item => statusColors[item.value]?.color50),
            hoverBorderWidth: 4,
            hoverBorderColor: "#A0A0A080"
        },
    ]
})

const barChartData = ref({
    labels: ['Authority', 'UBM', 'AW'],
    datasets: [
        {
            data: [],
            backgroundColor: ['#1463bd', '#cf750e', '#c5252d'],
            hoverBorderWidth: 3,
            hoverBorderColor: '#aaaaaa',
        },
    ]
})

const lineChartPoint = ref({
    x: null,
    y: null
})
const lineChartData = ref({
    datasets: [
        {
            label: "Now",
            data: [],
            borderColor: 'black',
            backgroundColor: 'red',
            pointRadius: 6,
            pointHoverRadius: 9,
        },
        {
            label: "Scheduled",
            data: [],
            backgroundColor: 'gray',
            borderColor: 'gray',
            borderDash: [3, 3],
            tension: 0.2,
            pointRadius: 2,
            pointHoverRadius: 5,
        },
        {
            label: "Actual",
            data: [],
            backgroundColor: 'orange',
            borderColor: 'orange',
            tension: 0.2,
            pointRadius: 2,
            pointHoverRadius: 5,
        },

    ]
})

const viewPercentage = (context: any) => {
    const meta = context.chart.getDatasetMeta(0)
    const dataset = context.dataset.data

    const visibleData = dataset.filter((_: any, i: number) => !context.chart._hiddenIndices?.[i])
    const visibleTotal = visibleData.reduce((a: number, b: number) => a + b, 0)
    const value = context.raw

    const percentage = ((value / visibleTotal) * 100).toFixed(1)
    return `${value} (%${percentage})`
}

const barChartOptions = {
    responsive: false,
    maintainAspectRatio: false,
    aspectRatio: 1,
    plugins: {
        legend: {
            display: false,
            position: 'right',
            labels: {
                boxWidth: 20,
                usePointStyle: true
            },
            align: 'center'
        },
        title: {
            display: true,
            text: 'Document Pending Days'
        },
        tooltip: {
            callbacks: {
                label: viewPercentage
            }
        },
    }
}

let statusCounter = ref<Record<string, any>>({})

function buildPieDataset(source: Record<string, number>) {
    const dataset = [
        (source['to_be_issued'] || 0) + (SHOW_DELAYED_COMPDOCS ? 0 : (source['delayed'] || 0)),
        source['airworthiness_review'] || 0,
        source['to_be_re-submitted'] || 0,
        source['to_be_updated'] || 0,
        source['authority_review'] || 0,
        source['authority_approved'] || 0
    ]

    if (SHOW_DELAYED_COMPDOCS) dataset.push(source['delayed'] || 0)
    return dataset
}


const rowHoverID = ref(null)
const rowPropsAttr = (rowData: Record<string, any>, rowIndex: number) => {
    return {
        style: {
            userSelect: 'none',
            '--n-td-text-color': rowHoverID.value === rowIndex ? 'rgba(255, 96, 96, 0.82)' : '--n-text-color'
        },
        onDblclick: () => {
            if (rowHoverID.value == rowIndex) {
                pieChartData.value.datasets[0].data = buildPieDataset(statusCounter.value)
                rowHoverID.value = null
            } else {
                console.log(rowData)
                pieChartData.value.datasets[0].data = buildPieDataset(rowData)
                rowHoverID.value = rowIndex
            }
        },
    }
}

const calculatedLineChart = ref<Record<string, any>>({})

function calculate(compdocs: ICompDoc[]) {
    const calculatedBarChart = calculateBarChart(compdocs)
    barChartData.value.datasets[0].data = [
        calculatedBarChart['authority'],
        calculatedBarChart['ubm'],
        calculatedBarChart['aw']
    ]

    statusCounter.value = calculatePieChart(compdocs)
    statusCounter.value['total'] = Object.values(statusCounter.value).reduce((a, b) => a + b, 0)

    pieChartData.value.datasets[0].data = buildPieDataset(statusCounter.value)

    calculatedLineChart.value = calculateLineChart(compdocs)
    lineChartData.value.datasets[0].data = calculatedLineChart.value["today"]
    lineChartData.value.datasets[1].data = calculatedLineChart.value["scheduled"]
    lineChartData.value.datasets[2].data = calculatedLineChart.value["actual"]
    calculatePanels(compdocs)

    calculatePerformanceMetrics()
}

const performanceMetrics = ref<Record<string, Record<string, any>>>({
    scheduled: {},
    actual: {},
    approved: {},
})
function calculatePerformanceMetrics() {
    performanceMetrics.value["scheduled"]["filled"] = statusCounter.value['total'] - (calculatedLineChart.value['lastScheduled']?.y || 0)
    performanceMetrics.value["scheduled"]["empty"] = calculatedLineChart.value['lastScheduled']?.y || 0
    performanceMetrics.value["scheduled"]["percentage"] = Math.ceil((statusCounter.value['total'] - (calculatedLineChart.value['lastScheduled']?.y || 0)) / statusCounter.value['total'] * 100)

    performanceMetrics.value["actual"]["filled"] = statusCounter.value['total'] - ((statusCounter.value['to_be_issued'] || 0) + (statusCounter.value['delayed'] || 0))
    performanceMetrics.value["actual"]["empty"] = (statusCounter.value['to_be_issued'] || 0) + (statusCounter.value['delayed'] || 0)
    performanceMetrics.value["actual"]["percentage"] = Math.ceil((statusCounter.value['total'] - ((statusCounter.value['to_be_issued'] || 0) + (statusCounter.value['delayed'] || 0))) / statusCounter.value['total'] * 100)

    performanceMetrics.value["approved"]["filled"] = statusCounter.value['authority_approved']
    performanceMetrics.value["approved"]["empty"] = statusCounter.value['total'] - statusCounter.value['authority_approved']
    performanceMetrics.value["approved"]["percentage"] = Math.ceil(statusCounter.value['authority_approved'] / statusCounter.value['total'] * 100)
}

function calculatePanels(compdocs: ICompDoc[]) {
    const panels: Record<string, any> = {};

    for (const compdoc of compdocs) {
        const panelName = compdoc["panel"];
        if (panelName) {
            if (!panels[panelName]) {
                panels[panelName] = { "panel": panelName }
            }

            if (compdoc.status_flow.length > 0) {
                const status = compdoc.status_flow[compdoc.status_flow.length - 1].status
                panels[panelName][status] = (panels[panelName][status] || 0) + 1
            }
        }
    }

    const sortedPanels = Object.values(panels).sort((a, b) => a.panel.localeCompare(b.panel, 'tr'));
    panelStatus.value = sortedPanels
}

onMounted(() => {
    const savedTab = localStorage.getItem("allSummaryActiveTab") || "ozgur"
    activeTab.value = savedTab
    compStore.setProjectName(savedTab)
    compStore.fetchCompdocs().then(() => {
        calculate(compStore.getCompdocs)
    })
})

const handleTabChange = (tab: string) => {
    rowHoverID.value = null
    localStorage.setItem('allSummaryActiveTab', tab);
    activeTab.value = tab;
    compStore.setProjectName(tab)
    compStore.fetchCompdocs().then(() => {
        calculate(compStore.getCompdocs)
    })
};

function onAfterLeave() {
    //activeTab.value = null
}

</script>

<style scoped>
:deep(.n-data-table-th) {
    position: sticky;
    top: 0;
    z-index: 2;
    background-color: 'green' !important
}

.bar-filled {
    background-color: rgba(0, 255, 0, 0.75);
    transition: grid-column 0.6s ease-out;
    border-radius: 8px 0px 0px 8px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.bar-empty {
    background-color: rgba(255, 0, 0, 0.75);
    transition: grid-column 0.6s ease-out;
    border-radius: 0px 8px 8px 0px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.bar-filled.full,
.bar-empty.full {
    border-radius: 8px 8px 8px 8px;
}

.dual-progress {
    position: relative;
    width: 100%;
}

.dual-progress-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    pointer-events: none;
    font-size: 12px;
    line-height: 1;
}

.seg {
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: visible;
}

.label {
    white-space: nowrap;
    font-weight: 400;
    text-shadow: 0 0 2px rgba(0, 0, 0, 0.25);
}

.label--filled {
    color: #fff
}

.label--empty {
    color: #fff
}
</style>
