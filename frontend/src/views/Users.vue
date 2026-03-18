<script setup lang="ts">
import { h, ref, onMounted, onUnmounted } from 'vue'
import { DataTableColumns, NButton, NDataTable, NSpace, NTag, NUpload } from 'naive-ui'
import { useAuthStore } from '@/stores/api'
import { IUser, IPermission } from '@/models/auth'
import UpdateForm from '@/components/user/UserPopup.vue';
import Details from '@/components/user/DetailedInfo.vue';
import Unauthorized from '@/views/Unauthorized.vue';
import { Home20Regular } from '@vicons/fluent';
import { useUserStore } from '@/stores/user';
import { isoToTurkishDateTime } from '@/utils/time'
import { getStringFilterFunc, getStringFilterMenuFunc } from '@/stores/datatable';

const pagination = {
  pageSize: 12
}

const store = useAuthStore()
const userStore = useUserStore()

const popupComponent = ref()
const tableRef = ref()

const filterValue = ref<Record<string, any>>({} as IUser);
const hasPermission = ref(userStore.hasRole("auth", "view_user"))

const onFilter = (attrib: string, filterData: any) => {
  filterValue.value[attrib] = filterData
  filterAttr()
}

const columns: DataTableColumns<IUser> = [
  {
    type: 'expand',
    expandable: (row) => true,
    renderExpand: (row) => {
      return h(Details, { user: row })
    },
    width: 1
  },
  {
    title: 'Username',
    key: 'username',
    width: 6,
    renderFilterMenu: getStringFilterMenuFunc("username", filterValue, onFilter),
    filter: getStringFilterFunc("username"),
  },
  {
    title: 'Email',
    key: 'email',
    width: 12,
    renderFilterMenu: getStringFilterMenuFunc("email", filterValue, onFilter),
    filter: getStringFilterFunc("email"),
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'First Name',
    key: 'first_name',
    width: 8,
    renderFilterMenu: getStringFilterMenuFunc("first_name", filterValue, onFilter),
    filter: getStringFilterFunc("first_name"),
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Last Name',
    key: 'last_name',
    width: 8,
    renderFilterMenu: getStringFilterMenuFunc("last_name", filterValue, onFilter),
    filter: getStringFilterFunc("last_name"),
    ellipsis: {
      tooltip: true
    },
  },
  {
    title: 'Last Login',
    key: 'last_login',
    width: 8,
    renderFilterMenu: getStringFilterMenuFunc("last_login", filterValue, onFilter),
    filter: getStringFilterFunc("last_login"),
    render(row: IUser) {
      return isoToTurkishDateTime(row.last_login)
    }
  },
  {
    title: 'Action',
    key: 'actions',
    width: 12,
    render(row: IUser) {
      return [h(
        NButton,
        {
          ghost: true,
          size: 'small',
          type: 'warning',
          focusable: false,
          onClick: () => {
            popupComponent.value.openModal(row)
          },
          style: "margin-right: 5px"
        },
        { default: () => 'Update' }
      ), h(
        NButton,
        {
          ghost: true,
          size: 'small',
          type: 'error',
          focusable: false,
          style: "margin-right: 5px",
          onClick: () => {
            window.$dialog.warning({
              title: "Delete",
              content: "Are you sure to delete?",
              positiveText: "Yes",
              negativeText: "No",
              onPositiveClick: () => {
                store.deleteUser(row.id).then(() => {
                  console.log("Request deleted: ", row.username)
                }).catch((err: any) => {
                  console.error("Error while deleting ", row.username, ": ", err)
                })
              },
            })
          }
        },
        { default: () => 'Delete' }
      )]
    }
  }
]

function filterAttr() {
  tableRef.value.filter(filterValue.value)
}

onMounted(() => {
  if (hasPermission.value) {
    store.fetchUsers()
    store.fetchPermissions()
  }
})

onUnmounted(() => {
  store.clearList()
})

</script>

<template>
  <div v-if="hasPermission">
    <n-flex justify="end">
      <n-text><strong>Total: </strong>{{ store.getUsers.length }}</n-text>
    </n-flex>
    <n-data-table ref="tableRef" :loading="store.isLoading" striped :columns="columns" :data="store.getUsers"
      :pagination="pagination" :row-key="(row: IUser) => row.id" />
    <UpdateForm ref="popupComponent" />
  </div>
  <div v-else>
    <Unauthorized />
  </div>
</template>