import type { RouteComponent, RouteRecordRaw } from 'vue-router'
import LoginView from '@/features/session/pages/Login.vue'
import Welcome from '@/app/pages/Welcome.vue'
import { navigationAccessPolicy } from '@/features/session/services/accessPolicy'

/** Return a Vue Router-native lazy component loader. */
function lazyRoute(loader: () => Promise<RouteComponent>) {
  return loader
}

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/welcome' },
  { path: '/welcome', name: 'welcome', meta: { public: true }, component: Welcome },
  { path: '/home', name: 'home', component: lazyRoute(() => import('@/app/pages/Home.vue')) },
  {
    path: '/integrations',
    name: 'integrations',
    component: lazyRoute(() => import('@/features/integrations/pages/IntegrationHub.vue'))
  },
  {
    path: '/jobs',
    name: 'jobs',
    component: lazyRoute(() => import('@/features/jobs/pages/JobCenter.vue'))
  },
  {
    path: '/accelerator',
    name: 'workflowAccelerator',
    meta: { access: navigationAccessPolicy('/accelerator') },
    component: lazyRoute(() => import('@/features/jobs/pages/WorkflowAccelerator.vue'))
  },
  {
    path: '/accelerator/outlook',
    name: 'acceleratorOutlook',
    meta: { access: navigationAccessPolicy('/accelerator/outlook') },
    component: lazyRoute(() => import('@/features/jobs/pages/WorkflowAccelerator.vue'))
  },
  { path: '/outlook', redirect: '/accelerator/outlook' },
  {
    path: '/task/ecr',
    name: 'ecrTask',
    meta: { access: navigationAccessPolicy('/accelerator/outlook') },
    component: lazyRoute(() => import('@/features/dcc/components/EcrTask.vue'))
  },
  {
    path: '/doors/scripter',
    name: 'doorsScripter',
    component: lazyRoute(() => import('@/features/tools/pages/doors/DoorsScripter.vue'))
  },
  {
    path: '/doors/agent',
    name: 'doorsAgent',
    component: lazyRoute(() => import('@/features/tools/pages/doors/DoorsAgent.vue'))
  },
  {
    path: '/developer/doors',
    name: 'developerDoors',
    meta: { access: navigationAccessPolicy('/developer/doors') },
    component: lazyRoute(() => import('@/features/tools/pages/doors/DoorsDeveloper.vue'))
  },
  {
    path: '/teamcenter/agent',
    name: 'teamcenterAgent',
    component: lazyRoute(() => import('@/features/tools/pages/teamcenter/TeamcenterAgent.vue'))
  },
  {
    path: '/doors/poclinker',
    name: 'pocLinker',
    component: lazyRoute(() => import('@/features/tools/pages/doors/PocLinker.vue'))
  },
  ...comparisonRoutes(),
  {
    path: '/media-converter',
    name: 'mediaConverter',
    component: lazyRoute(() => import('@/features/tools/pages/MediaConverter.vue'))
  },
  {
    path: '/translator',
    name: 'translator',
    component: lazyRoute(() => import('@/features/tools/pages/Translator.vue'))
  },
  {
    path: '/pdf/split',
    name: 'pdfSplit',
    component: lazyRoute(() => import('@/features/tools/pages/PdfSplit.vue'))
  },
  {
    path: '/pptxGallery',
    name: 'pptxGallery',
    component: lazyRoute(() => import('@/features/tools/pages/Presentations.vue'))
  },
  {
    path: '/organization',
    name: 'organization',
    component: lazyRoute(() => import('@/features/organization/pages/Organization.vue'))
  },
  { path: '/login', name: 'login', meta: { public: true }, component: LoginView },
  {
    path: '/invite',
    name: 'invitation',
    meta: { public: true },
    component: lazyRoute(() => import('@/features/session/pages/InviteRegistration.vue'))
  },
  {
    path: '/users',
    name: 'users',
    meta: { access: navigationAccessPolicy('/users') },
    component: lazyRoute(() => import('@/features/session/pages/Users.vue'))
  },
  {
    path: '/jira',
    name: 'jira',
    component: lazyRoute(() => import('@/features/dcc/pages/Jira.vue'))
  },
  {
    path: '/ddfAssistant',
    name: 'ddfAssistant',
    meta: { access: navigationAccessPolicy('/ddfAssistant') },
    component: lazyRoute(() => import('@/features/tools/pages/DDFAssistant.vue'))
  },
  {
    path: '/compdocs',
    children: [
      {
        name: 'compdocsHome',
        path: 'home',
        component: lazyRoute(() => import('@/features/compliance/pages/Home.vue'))
      },
      {
        name: 'compdocs',
        path: ':project',
        component: lazyRoute(() => import('@/features/compliance/pages/CompDocTable.vue'))
      }
    ]
  },
  {
    path: '/compdocs/coverpagecreator',
    name: 'coverpagecreator',
    component: lazyRoute(() => import('@/features/compliance/pages/CoverPageCreator.vue'))
  },
  {
    path: '/compdocs/docAnalyzer',
    name: 'docAnalyzer',
    component: lazyRoute(() => import('@/features/compliance/pages/DocAnalyzer.vue'))
  },
  {
    path: '/settings',
    name: 'settings',
    component: lazyRoute(() => import('@/features/session/pages/Settings.vue'))
  },
  {
    path: '/unauthorized',
    name: 'unauthorized',
    component: lazyRoute(() => import('@/features/session/pages/Unauthorized.vue'))
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: lazyRoute(() => import('@/app/pages/NotFound.vue'))
  }
]

function comparisonRoutes(): RouteRecordRaw[] {
  return [
    {
      path: '/compare/excel',
      name: 'excelCompare',
      component: lazyRoute(() => import('@/features/tools/pages/compare/ExcelCompare.vue'))
    },
    {
      path: '/compare/word',
      name: 'wordCompare',
      component: lazyRoute(() => import('@/features/tools/pages/compare/WordCompare.vue'))
    },
    {
      path: '/compare/pdf',
      name: 'pdfCompare',
      component: lazyRoute(() => import('@/features/tools/pages/compare/PdfCompare.vue'))
    }
  ]
}
