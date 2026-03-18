import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/Login.vue'
import Settings from '@/views/Settings.vue'
import CompDoc from '@/views/CompDocTable.vue'
import ECDMaster from '@/views/ECDContainer.vue'
import Welcome from '@/views/Welcome.vue'
import Users from '@/views/Users.vue'
import DoorsAgent from '@/views/doors/DoorsAgent.vue'
import DoorsScripter from '@/views/doors/DoorsScripter.vue'
import PocLinker from '@/views/doors/PocLinker.vue'
import DDFAssistant from '@/views/DDFAssistant.vue'
import OrgsContainer from '@/views/OrgsContainer.vue'
import ExcelCompare from '@/views/compare/ExcelCompare.vue'
import WordCompare from '@/views/compare/WordCompare.vue'
import PptxGallery from '@/views/PptxGallery.vue'
import PdfSplit from '@/views/PdfSplit.vue'
import OutlookContainer from '@/views/OutlookContainer.vue'
import CoverPageCreator from '@/views/compdoc/CoverPageCreator.vue'
import Home from '@/views/Home.vue'

import { isAuthenticated } from '@/stores/user'
import EcrTask from '@/components/outlook/EcrTask.vue'
import PdfCompare from '@/views/compare/PdfCompare.vue'
import Translator from '@/views/Translator.vue'


const router = createRouter({
  //history: createWebHistory(import.meta.env.BASE_URL),
  history: createWebHistory('/app/'),
  routes: [
    {
      path: '/',
      redirect: '/welcome',
    },
    {
      path: '/welcome',
      name: 'welcome',
      component: Welcome
    },
    {
      path: '/home',
      name: 'home',
      component: Home
    },
    {
      path: '/outlook',
      name: 'outlook',
      component: OutlookContainer
    },
    {
      path: '/task/ecr',
      name: 'ecrTask',
      component: EcrTask
    },
    {
      path: '/doors/scripter',
      name: 'doorsScripter',
      component: DoorsScripter
    },
    {
      path: '/doors/agent',
      name: 'doorsAgent',
      component: DoorsAgent
    },
    {
      path: '/doors/poclinker',
      name: 'pocLinker',
      component: PocLinker
    },
    {
      path: '/compare/excel',
      name: 'excelCompare',
      component: ExcelCompare
    },
    {
      path: '/compare/word',
      name: 'wordCompare',
      component: WordCompare
    },
    {
      path: '/compare/pdf',
      name: 'pdfCompare',
      component: PdfCompare
    },
    {
      path: '/translator',
      name: 'translator',
      component: Translator
    },
    {
      path: '/pdf/split',
      name: 'pdfSplit',
      component: PdfSplit
    },
    {
      path: '/pptxGallery',
      name: 'pptxGallery',
      component: PptxGallery
    },
    {
      path: '/organization',
      name: 'organization',
      component: OrgsContainer
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView
    },
    {
      path: '/users',
      name: 'users',
      meta: { auth: true },
      component: Users,
    },
    {
      path: '/dcc',
      name: 'dcc',
      component: ECDMaster,
    },
    {
      path: '/ddfAssistant',
      name: 'ddfAssistant',
      component: DDFAssistant,
    },
    {
      path: '/compdocs',
      meta: { auth: true },
      children: [
        {
          name: 'compdocs',
          path: ':project',
          component: CompDoc,
        }
      ]
    },
    {
      path: '/compdocs/coverpagecreator',
      name: 'coverpagecreator',
      component: CoverPageCreator,
    },
    {
      path: '/settings',
      name: 'settings',
      component: Settings,
      meta: { auth: true }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/views/NotFound.vue')
    }
  ]
})

router.beforeEach((to, from, next) => {
  if (to.meta.auth && !isAuthenticated()) {
    next({name: "login"})
  } else if (to.name == "login" && isAuthenticated()) {
    next({name: "home"})
  } else {
    next()
  }
})

export default router
