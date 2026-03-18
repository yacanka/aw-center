import { h, ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { NButton, NDataTable, NSpace, NTag, NUpload, NIcon, NEllipsis, NTooltip, NSpin, NText, NInput, NFormItem, NForm, NDatePicker, NSelect, NCheckboxGroup, NCheckbox, NDivider, NSwitch } from 'naive-ui'
import { toTitleCase } from '@/utils/text'
import { getDaysDifference, parseDateFlex, getTodayEUFormat } from '@/utils/time'
import { getType, nullCheck } from '@/utils/general'
import { StepsInjection } from 'naive-ui/es/steps/src/Steps'
import { FilterOptionValue } from 'naive-ui/es/data-table/src/interface'

const SHOW_DELAYED_COMPDOCS = import.meta.env.SHOW_DELAYED_COMPDOCS

const dateFilterOptions = [
    { value: 'equals', label: 'Equals' },
    { value: 'does_not_equal', label: 'Does Not Equal' },
    { value: 'is_after', label: 'Is After' },
    { value: 'is_after_or_equal_to', label: 'Is After Or Equal To' },
    { value: 'is_before', label: 'Is Before' },
    { value: 'is_before_or_equal_to', label: 'Is Before Or Equal To' },
]

const dateFilterOptionsMini = [
    { value: '==', label: '==' },
    { value: '!=', label: '!=' },
    { value: '>', label: '>' },
    { value: '>=', label: '>=' },
    { value: '<', label: '<' },
    { value: '<=', label: '<=' },
]

export const statusOptions = [
    { value: 'to_be_issued', label: 'To be Issued' },
    { value: 'airworthiness_review', label: 'Airworthiness Review' },
    { value: 'to_be_re-submitted', label: 'To be Re-Submitted' },
    { value: 'to_be_updated', label: 'To be Updated' },
    { value: 'authority_review', label: 'Authority Review' },
    { value: 'authority_approved', label: 'Authority Approved' },
]
if (SHOW_DELAYED_COMPDOCS) {
    statusOptions.push({ value: 'delayed', label: 'Delayed' })
}

export const statusColors: Record<string, any> = {
    'to_be_issued': { color: "#FFC7CE", color25: "#FFC7CE40", color50: "#FFC7CE80", color75: "#FFC7CEbf" },
    'airworthiness_review': { color: "#FFEB9C", color25: "#FFEB9C40", color50: "#FFEB9C80", color75: "#FFEB9Cbf" },
    'to_be_re-submitted': { color: "#ED7D31", color25: "#ED7D3140", color50: "#ED7D3180", color75: "#ED7D31bf" },
    'to_be_updated': { color: "#FFF2CC", color25: "#FFF2CC40", color50: "#FFF2CC80", color75: "#FFF2CCbf" },
    'authority_review': { color: "#00B0F0", color25: "#00B0F040", color50: "#00B0F080", color75: "#00B0F0bf" },
    'authority_approved': { color: "#C6EFCE", color25: "#C6EFCE40", color50: "#C6EFCE80", color75: "#C6EFCEbf" },
    'delayed': { color: "#FFC7CE", color25: "#FFC7CE40", color50: "#FFC7CE80", color75: "#FFC7CEbf" },
}

export const mocOptions = [
    { value: '0', label: '0' },
    { value: '1', label: '1' },
    { value: '2', label: '2' },
    { value: '3', label: '3' },
    { value: '4', label: '4' },
    { value: '5', label: '5' },
    { value: '6', label: '6' },
    { value: '7', label: '7' },
    { value: '8', label: '8' },
    { value: '9', label: '9' },
    { value: 'M', label: 'M' },
]

export const catOptions = [
    { value: "1", label: "1" },
    { value: "2", label: "2" },
    { value: "3", label: "3" },
    { value: "not_retained", label: "Not Retained" },
    { value: "retained", label: "Retained" },
]

const dateFilterContainer = ref<Record<string, any>>({})
const arrayFilterContainer = ref<Record<string, any>>({})

export function createEmpty() {
    return {
        id: 0,
        name: '',
        panel: null,
        signature_panel: [],
        ata: null,
        cover_page_no: '',
        cover_page_issue: '',
        tech_doc_no: '',
        tech_doc_issue: '',
        delivered_tech_doc_issue: '',
        tech_doc_no_2: '',
        tech_doc_issue_2: '',
        delivered_tech_doc_issue_2: '',
        responsible: '',
        cat: null,
        moc: null,
        mom_no: '',
        requirements: [],
        status_flow: [],
        status: '',
        ubm_target_date: '',
        ubm_delivery_date: '',
        path: '',
        notes: '',
        authority_sharing_number: '',
        created_time: '',
        history: []
    };
}

export function getDateFilterMenuFunc(attrib: string, onApplyEvent: any, onCleanEvent: any) {
    const dateFilterMenuFunc = (actions: any) => {

        if (dateFilterContainer.value[attrib] == null) dateFilterContainer.value[attrib] = { filter: false }

        const onFilter = () => {
            dateFilterContainer.value[attrib]['filter'] = true
            onApplyEvent?.(attrib, dateFilterContainer.value[attrib])
        }

        const onClean = () => {
            onCleanEvent?.(attrib)
            dateFilterContainer.value[attrib] = { filter: false }
            actions.hide()
        }

        return h(
            NSpace,
            {
                style: {
                    padding: "8px",
                }
            },
            {
                default: () => [
                    h(NSelect, {
                        options: dateFilterOptionsMini,
                        clearable: false,
                        placeholder: 'Type',
                        style: {
                            width: "64px"
                        },
                        size: "tiny",
                        multiple: false,
                        value: dateFilterContainer.value[attrib]?.type || null,
                        'onUpdate:value': (val) => {
                            dateFilterContainer.value[attrib].type = val
                        }
                    }),
                    h(NDatePicker, {
                        'formatted-value': dateFilterContainer.value[attrib]?.date || null,
                        'onUpdate:formatted-value': (val: string) => {
                            dateFilterContainer.value[attrib].date = val
                        },
                        firstDayOfWeek: 0,
                        clearable: false,
                        type: 'date',
                        size: 'tiny',
                        format: "dd.MM.yyyy",
                        style: { width: '96px' }
                    }),
                    h(NButton, {
                        type: dateFilterContainer.value[attrib]['filter'] ? 'error' : (!dateFilterContainer.value[attrib]?.date || !dateFilterContainer.value[attrib]?.type ? 'default' : 'success'),
                        disabled: !dateFilterContainer.value[attrib]?.date || !dateFilterContainer.value[attrib]?.type,
                        onClick: dateFilterContainer.value[attrib]['filter'] ? onClean : onFilter,
                        size: "tiny",
                        style: { width: '48px' }
                    }, () => dateFilterContainer.value[attrib]['filter'] ? 'Clean' : 'Apply')
                ]
            }
        )
    }

    return dateFilterMenuFunc
}
export function getArrayFilterMenuFunc(attrib: string, onApplyEvent: any, onCleanEvent: any) {
    const arrayFilterMenuFunc = (actions: any) => {

        if (arrayFilterContainer.value[attrib] == null) arrayFilterContainer.value[attrib] = { values: [], filter: false }

        const onFilter = () => {
            arrayFilterContainer.value[attrib]['filter'] = true
            onApplyEvent?.(attrib, arrayFilterContainer.value[attrib].values)
        }

        const onClean = () => {
            onCleanEvent?.(attrib)
            arrayFilterContainer.value[attrib] = { values: [], filter: false }
            actions.hide()
        }

        return h(
            NSpace,
            {
                vertical: true,
                style: {
                    padding: "8px",
                }
            },
            {
                default: () => [
                    h(
                        NCheckboxGroup,
                        {
                            value: arrayFilterContainer.value[attrib].values,
                            onUpdateValue: (val) => {
                                arrayFilterContainer.value[attrib].values = val
                            },
                        },
                        () => {
                            return h(NSpace,
                                {
                                    vertical: true,
                                    style: {
                                        padding: "8px",
                                    }
                                },
                                () => {
                                    return statusOptions.map(option =>
                                        h(
                                            NCheckbox,
                                            {
                                                key: option.value,
                                                value: option.value,
                                                label: option.label
                                            },
                                            {}
                                        )
                                    )
                                }
                            )
                        }
                    ),
                    h(NDivider, { style: { margin: '0px' } }, {}),
                    h(NButton, {
                        type: arrayFilterContainer.value[attrib]['filter'] ? 'error' : (!arrayFilterContainer.value[attrib]?.values.length ? 'default' : 'success'),
                        disabled: !arrayFilterContainer.value[attrib]?.values.length,
                        onClick: arrayFilterContainer.value[attrib]['filter'] ? onClean : onFilter,
                        size: "tiny",
                        style: { width: '48px' }
                    }, () => arrayFilterContainer.value[attrib]['filter'] ? 'Clean' : 'Apply')
                ]
            }
        )
    }

    return arrayFilterMenuFunc
}

export function getStringFilterMenuFunc(attrib: string, filterValue: any, onUpdate: any) {
    const renderFilterMenuFunc = (actions: any) => {
        const inputRef = ref()

        nextTick(() => {
            inputRef.value?.focus()
        })

        return h(NInput, {
            ref: inputRef,
            value: filterValue.value[attrib],
            size: "small",
            style: "margin: 5px; width: 180px",
            placeholder: "Filter " + toTitleCase(attrib.replaceAll("_", " ")),
            clearable: true,
            'onUpdate:value': (val) => {
                onUpdate?.(attrib, (val || null))
            },
        })
    }
    return renderFilterMenuFunc
}

export function getBooleanFilterMenuFunc(attrib: string, filterValue: any, onUpdate: any) {
    const renderFilterMenuFunc = (actions: any) => {
        const inputRef = ref()

        return h(NSwitch, {
            ref: inputRef,
            value: filterValue.value[attrib],
            size: "small",
            style: "margin: 5px; width: 40px",
            'onUpdate:value': (val) => {
                onUpdate?.(attrib, val)
            },
        })
    }
    return renderFilterMenuFunc
}

export function getStringFilterFunc(attrib: string) {
    const filterFunc = (value: FilterOptionValue, row: Record<string, any>) => {
        if (nullCheck(row[attrib])) return false
        return Boolean(~row[attrib].indexOf(value as string))
    }
    return filterFunc
}

export function getBooleanFilterFunc(attrib: string) {
    const filterFunc = (value: FilterOptionValue, row: Record<string, any>) => {
        if (nullCheck(row[attrib])) return false
        return row[attrib] == value
    }
    return filterFunc
}

export function getArrayFilterFunc(attrib: string) {
    const arrayFilterFunc = (value: string[], row: Record<string, any>) => {
        if (nullCheck(row[attrib])) return false
        if (getType(value) == 'array') return value.length > 0 ? value.some(item => ~row[attrib].indexOf(item)) : true
        //return value.length > 0 ? row[attrib] == value : true
        return ~row[attrib].indexOf(value)
    }
    return arrayFilterFunc
}

export function getDateFilterFunc(attrib: string) {
    const filterFunc = (value: { date: string, type: string }, row: Record<string, any>) => {
        if (nullCheck(row[attrib])) return false

        if (nullCheck(value.date) || nullCheck(value.type)) return true

        const diff = getDaysDifference(row[attrib], value.date)
        if (!diff) return false

        if (value.type == '==' && diff == 0) return true
        if (value.type == '!=' && diff != 0) return true
        if (value.type == '>=' && diff >= 0) return true
        if (value.type == '<=' && diff <= 0) return true
        if (value.type == '>' && diff > 0) return true
        if (value.type == '<' && diff < 0) return true

        return false
    }
    return filterFunc
}