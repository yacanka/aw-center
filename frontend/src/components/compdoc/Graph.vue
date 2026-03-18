<template>
    <n-modal v-model:show="showModal" preset="dialog" title="Document Summary" :on-after-leave="onAfterLeave"
        :style="{ width: '600px' }">
        <div style="height: 440px; display: flex; align-items: center;">
            <n-tabs placement="top" v-model:value="activeTab" @update:value="handleTabChange">
                <n-tab-pane name="pie" tab="Pie Chart">
                    <Pie :data="pieChartData" :options="pieChartOptions" :width="480" :height="360" />
                </n-tab-pane>
                <n-tab-pane name="bar" tab="Bar Chart">
                    <Bar :data="barChartData" :options="barChartOptions" :width="480" :height="360" />
                </n-tab-pane>
                <n-tab-pane name="line" tab="Burndown Graph">
                    <Line :data="lineChartData" :options="getLineChartOptions(null, null)" :width="540" :height="360" />
                </n-tab-pane>
            </n-tabs>
        </div>

        <template #action>
            <n-button :onClick="closeModal"> OK </n-button>
        </template>
    </n-modal>
</template>

<script setup>
import { ref, onMounted, onUnmounted, reactive } from 'vue'
import { Pie, Bar, Line, Scatter } from 'vue-chartjs'
import annotationPlugin from 'chartjs-plugin-annotation'
import { statusOptions, statusColors} from '@/stores/datatable'
import { calculateBarChart, calculatePieChart, calculateLineChart, pieChartOptions, barChartOptions, getLineChartOptions } from '@/stores/chartStore'
import {
    Chart as ChartJS,
    Title,
    Tooltip,
    Legend,
    LineElement,
    BarElement,
    CategoryScale,
    LinearScale,
    PointElement,
    ArcElement,
    TimeScale
} from 'chart.js'
ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale, ArcElement, PointElement, LineElement, TimeScale, annotationPlugin)

const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS
const showModal = ref(false);
const activeTab = ref(null)
const pieChartData = ref({
    labels: statusOptions.map(item => item.label),
    datasets: [
        {
            data: [],
            radius: '90%',
            backgroundColor: statusOptions.map(item => statusColors[item.value].color75),
            hoverBorderWidth: 3,
            hoverBorderColor: '#aaaaaa',
        },
    ]
})

const barChartData = ref({
    labels: ['Authority', 'UBM', 'AW'],
    datasets: [
        {
            data: [],
            radius: '90%',
            backgroundColor: ['#1463bd', '#cf750e', '#c5252d'],
            hoverBorderWidth: 3,
            hoverBorderColor: '#aaaaaa',
        },
    ]
})

const lineChartData = ref({
    datasets: [
        {
            label: "Now",
            data: [{ x: "2025-08-05", y: 30 }],
            borderColor: 'black',
            backgroundColor: 'red',
            pointBorderColor: 'black',
            pointBackgroundColor: 'red',
            pointRadius: 6,
            pointHoverRadius: 9,
        },
        {
            label: "Scheduled",
            data: [],
            backgroundColor: 'gray',
            borderColor: 'gray',
            borderDash: [5, 5],
            tension: 0.2
        },
        {
            label: "Actual",
            data: [40, 39, 10, 40, 80, 70],
            backgroundColor: 'orange',
            borderColor: 'orange',
            tension: 0.2
        },

    ]
})

function openModal(compdocs) {
    showModal.value = true

    const calculatedBarChart = calculateBarChart(compdocs)
    barChartData.value.datasets[0].data = [
        calculatedBarChart['authority'],
        calculatedBarChart['ubm'],
        calculatedBarChart['aw']
    ]

    const calculatedPieChart = calculatePieChart(compdocs)
    pieChartData.value.datasets[0].data = [
        calculatedPieChart['to_be_issued'] + (SHOW_DELAYED_COMPDOCS ? 0 : calculatedPieChart['delayed']),
        calculatedPieChart['airworthiness_review'],
        calculatedPieChart['to_be_re-submitted'],
        calculatedPieChart['to_be_updated'],
        calculatedPieChart['authority_review'],
        calculatedPieChart['authority_approved'],
    ]
    if(SHOW_DELAYED_COMPDOCS){
        pieChartData.value.datasets[0].data.push(calculatedPieChart['delayed'])
    }

    const calculatedLineChart = calculateLineChart(compdocs)
    lineChartData.value.datasets[0].data = calculatedLineChart["today"]
    lineChartData.value.datasets[1].data = calculatedLineChart["scheduled"]
    lineChartData.value.datasets[2].data = calculatedLineChart["actual"]
}

onMounted(() => {
    const savedTab = localStorage.getItem("summaryActiveTab")
    activeTab.value = (savedTab ? savedTab : 'bar');
})

const handleTabChange = (tab) => {
    localStorage.setItem('summaryActiveTab', tab);
    activeTab.value = tab;
};

function closeModal() {
    showModal.value = false;
}

function onAfterLeave() {
    //activeTab.value = null
}

defineExpose({
    openModal
})
</script>

<style>

</style>