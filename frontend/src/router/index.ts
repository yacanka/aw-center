import { defineAsyncComponent } from 'vue'
import { createRouter, createWebHistory, type RouteComponent } from 'vue-router'
import LoginView from '@/views/Login.vue'
import Welcome from '@/views/Welcome.vue'
import RouteLoading from '@/components/router/RouteLoading.vue'

import { isAuthenticated } from '@/stores/user'

const loadingDelayMilliseconds = 120

/**
 * Creates a route-level async component with a shared loading skeleton.
 */
function lazyRoute(loader: () => Promise<RouteComponent>) {
  return defineAsyncComponent({
    loader,
    loadingComponent: RouteLoading,
    delay: loadingDelayMilliseconds
  })
}

const router = createRouter({
  //history: createWebHistory(import.meta.env.BASE_URL),
  history: createWebHistory('/app/'),
  routes: [
    {
      path: '/',
      redirect: '/welcome'
    },
    {
      path: '/welcome',
      name: 'welcome',
      component: Welcome
    },
    {
      path: '/home',
      name: 'home',
      component: lazyRoute(() => import('@/views/Home.vue'))
    },
    {
      path: '/outlook',
      name: 'outlook',
      component: lazyRoute(() => import('@/views/OutlookContainer.vue'))
    },
    {
      path: '/task/ecr',
      name: 'ecrTask',
      component: lazyRoute(() => import('@/components/outlook/EcrTask.vue'))
    },
    {
      path: '/doors/scripter',
      name: 'doorsScripter',
      component: lazyRoute(() => import('@/views/doors/DoorsScripter.vue'))
    },
    {
      path: '/doors/agent',
      name: 'doorsAgent',
      component: lazyRoute(() => import('@/views/doors/DoorsAgent.vue'))
    },
    {
      path: '/developer/doors',
      name: 'developerDoors',
      component: lazyRoute(() => import('@/views/doors/DoorsDeveloper.vue'))
    },
    {
      path: '/teamcenter/agent',
      name: 'teamcenterAgent',
      component: lazyRoute(() => import('@/views/teamcenter/TeamcenterAgent.vue'))
    },
    {
      path: '/doors/poclinker',
      name: 'pocLinker',
      component: lazyRoute(() => import('@/views/doors/PocLinker.vue'))
    },
    {
      path: '/compare/excel',
      name: 'excelCompare',
      component: lazyRoute(() => import('@/views/compare/ExcelCompare.vue'))
    },
    {
      path: '/compare/word',
      name: 'wordCompare',
      component: lazyRoute(() => import('@/views/compare/WordCompare.vue'))
    },
    {
      path: '/compare/pdf',
      name: 'pdfCompare',
      component: lazyRoute(() => import('@/views/compare/PdfCompare.vue'))
    },
    {
      path: '/media-converter',
      name: 'mediaConverter',
      component: lazyRoute(() => import('@/views/MediaConverter.vue'))
    },
    {
      path: '/translator',
      name: 'translator',
      component: lazyRoute(() => import('@/views/Translator.vue'))
    },
    {
      path: '/pdf/split',
      name: 'pdfSplit',
      component: lazyRoute(() => import('@/views/PdfSplit.vue'))
    },
    {
      path: '/pptxGallery',
      name: 'pptxGallery',
      component: lazyRoute(() => import('@/views/PptxGallery.vue'))
    },
    {
      path: '/organization',
      name: 'organization',
      component: lazyRoute(() => import('@/views/OrgsContainer.vue'))
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
      component: lazyRoute(() => import('@/views/Users.vue'))
    },
    {
      path: '/dcc',
      name: 'dcc',
      component: lazyRoute(() => import('@/views/ECDContainer.vue'))
    },
    {
      path: '/ddfAssistant',
      name: 'ddfAssistant',
      component: lazyRoute(() => import('@/views/DDFAssistant.vue'))
    },
    {
      path: '/compdocs',
      meta: { auth: true },
      children: [
        {
          name: 'compdocs',
          path: ':project',
          component: lazyRoute(() => import('@/views/CompDocTable.vue'))
        }
      ]
    },
    {
      path: '/compdocs/coverpagecreator',
      name: 'coverpagecreator',
      component: lazyRoute(() => import('@/views/compdoc/CoverPageCreator.vue'))
    },
    {
      path: '/compdocs/docAnalyzer',
      name: 'docAnalyzer',
      component: lazyRoute(() => import('@/views/compdoc/DocAnalyzer.vue'))
    },
    {
      path: '/settings',
      name: 'settings',
      component: lazyRoute(() => import('@/views/Settings.vue')),
      meta: { auth: true }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: lazyRoute(() => import('@/views/NotFound.vue'))
    }
  ]
})

router.beforeEach((to, from, next) => {
  if (to.meta.auth && !isAuthenticated()) {
    next({ name: 'login' })
  } else if (to.name == 'login' && isAuthenticated()) {
    next({ name: 'home' })
  } else {
    next()
  }
})

export default router
