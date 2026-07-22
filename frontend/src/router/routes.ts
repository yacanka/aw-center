import type { RouteComponent, RouteRecordRaw } from 'vue-router'
import LoginView from '@/views/Login.vue'
import Welcome from '@/views/Welcome.vue'
import { navigationAccessPolicy } from '@/services/accessPolicy'

/** Return a Vue Router-native lazy component loader. */
function lazyRoute(loader: () => Promise<RouteComponent>) {
  return loader
}

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/welcome' },
  { path: '/welcome', name: 'welcome', meta: { public: true }, component: Welcome },
  { path: '/home', name: 'home', component: lazyRoute(() => import('@/views/Home.vue')) },
  {
    path: '/integrations',
    name: 'integrations',
    component: lazyRoute(() => import('@/views/IntegrationHub.vue'))
  },
  {
    path: '/jobs',
    name: 'jobs',
    component: lazyRoute(() => import('@/views/JobCenter.vue'))
  },
  {
    path: '/outlook',
    name: 'outlook',
    meta: { access: navigationAccessPolicy('/outlook') },
    component: lazyRoute(() => import('@/views/OutlookContainer.vue'))
  },
  {
    path: '/task/ecr',
    name: 'ecrTask',
    meta: { access: navigationAccessPolicy('/task/ecr') },
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
    meta: { access: navigationAccessPolicy('/developer/doors') },
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
  ...comparisonRoutes(),
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
  { path: '/login', name: 'login', meta: { public: true }, component: LoginView },
  {
    path: '/invite',
    name: 'invitation',
    meta: { public: true },
    component: lazyRoute(() => import('@/views/InviteRegistration.vue'))
  },
  {
    path: '/users',
    name: 'users',
    meta: { access: navigationAccessPolicy('/users') },
    component: lazyRoute(() => import('@/views/Users.vue'))
  },
  {
    path: '/jira',
    name: 'jira',
    component: lazyRoute(() => import('@/views/JiraContainer.vue'))
  },
  {
    path: '/ddfAssistant',
    name: 'ddfAssistant',
    meta: { access: navigationAccessPolicy('/ddfAssistant') },
    component: lazyRoute(() => import('@/views/DDFAssistant.vue'))
  },
  {
    path: '/compdocs',
    children: [
      {
        name: 'compdocsHome',
        path: 'home',
        component: lazyRoute(() => import('@/views/compdoc/Home.vue'))
      },
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
    component: lazyRoute(() => import('@/views/Settings.vue'))
  },
  {
    path: '/unauthorized',
    name: 'unauthorized',
    component: lazyRoute(() => import('@/views/Unauthorized.vue'))
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: lazyRoute(() => import('@/views/NotFound.vue'))
  }
]

function comparisonRoutes(): RouteRecordRaw[] {
  return [
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
    }
  ]
}
