import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import {
  create,
  NAlert,
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NDataTable,
  NEmpty,
  NFlex,
  NGi,
  NGrid,
  NProgress,
  NScrollbar,
  NSelect,
  NSpin,
  NStatistic,
  NTab,
  NTabs,
  NTag,
  NText
} from 'naive-ui'
import ViewerApp from './ViewerApp.vue'
import ViewerWorkspace from './ViewerWorkspace.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/:project?', name: 'dashboard', component: ViewerWorkspace },
    { path: '/:project/documents', name: 'compdocs', component: ViewerWorkspace },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

createApp(ViewerApp)
  .use(router)
  .use(
    create({
      components: [
        NAlert,
        NButton,
        NCard,
        NCollapse,
        NCollapseItem,
        NDataTable,
        NEmpty,
        NFlex,
        NGi,
        NGrid,
        NProgress,
        NScrollbar,
        NSelect,
        NSpin,
        NStatistic,
        NTab,
        NTabs,
        NTag,
        NText
      ]
    })
  )
  .mount('#viewer')
