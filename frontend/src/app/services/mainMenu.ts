import { h, type Component, type ComputedRef, type InjectionKey } from 'vue'
import { NIcon, type MenuOption } from 'naive-ui'
import {
  ArrowRepeatAll24Regular,
  ArrowReset24Regular,
  Book24Regular,
  Code24Regular,
  Cut24Regular,
  Document24Regular,
  Door20Regular,
  Edit24Regular,
  EyeTracking24Regular,
  FormNew24Regular,
  Glasses24Regular,
  Home24Regular,
  ImageMultiple24Regular,
  LinkSquare24Regular,
  Mail24Regular,
  People24Regular,
  PeopleAudience24Regular,
  Settings24Regular
} from '@vicons/fluent'
import { Excel, Pdf, Word } from '@/app/stores/iconStore'
import type { ProjectRegistryItem } from '@/features/projects/models/projectRegistry'
import type { IUser } from '@/features/session/models/auth'
import { filterNavigationByAccess } from '@/features/session/services/accessPolicy'

export type ProjectMenuOption = MenuOption & {
  name: string
  children?: ProjectMenuOption[]
}

export const MAIN_MENU_OPTIONS_KEY: InjectionKey<ComputedRef<ProjectMenuOption[]>> =
  Symbol('mainMenuOptions')

/** Build the application menu from the authorized project registry. */
export function createMainMenuOptions(
  projects: ProjectRegistryItem[],
  user: IUser,
  dccAvailable = false,
  organizationAvailable = false
): ProjectMenuOption[] {
  const options = [
    ...primaryOptions(),
    { key: 'divider1', type: 'divider', name: 'mainDivider' },
    ...workflowOptions(projects, dccAvailable, organizationAvailable),
    ...administrationOptions()
  ]
  return filterNavigationByAccess(options, user)
}

function primaryOptions(): ProjectMenuOption[] {
  return [
    menuItem('AW Center', '/home', 'aw center', Home24Regular),
    menuItem('Integration Hub', '/integrations', 'integrations', LinkSquare24Regular),
    menuItem('Job Center', '/jobs', 'jobs', ArrowRepeatAll24Regular)
  ]
}

function workflowOptions(
  projects: ProjectRegistryItem[],
  dccAvailable: boolean,
  organizationAvailable: boolean
): ProjectMenuOption[] {
  const options = [
    developerGroup(),
    groupItem(
      'Workflow Accelerator',
      '/accelerator',
      'workflowAccelerator',
      ArrowRepeatAll24Regular,
      [
        menuItem('Accelerator', '/accelerator', 'accelerator', ArrowRepeatAll24Regular),
        menuItem('Outlook Task', '/accelerator/outlook', 'outlook', Mail24Regular)
      ]
    ),
    doorsGroup(),
    menuItem('Teamcenter', '/teamcenter/agent', 'teamcenter', Glasses24Regular),
    compareGroup(),
    groupItem('Pdf', '/pdf', 'pdf', Pdf, [menuItem('Split', '/pdf/split', 'split', Cut24Regular)]),
    menuItem('Media Converter', '/media-converter', 'mediaConverter', ImageMultiple24Regular),
    menuItem('Translator', '/translator', 'translator', ArrowReset24Regular),
    menuItem('DDF Assistant', '/ddfAssistant', 'ddf', FormNew24Regular),
    menuItem('Powerpoint Gallery', '/pptxGallery', 'pptxgallery', ImageMultiple24Regular)
  ]
  if (projects.length) {
    options.splice(
      1,
      0,
      groupItem('Compliance Docs', '/compdocs', 'projects', Book24Regular, projectItems(projects))
    )
  }
  const jiraPosition = projects.length ? 3 : 2
  if (dccAvailable) {
    options.splice(jiraPosition, 0, menuItem('JIRA', '/jira', 'jira', EyeTracking24Regular))
  }
  if (organizationAvailable) {
    options.push(menuItem('Organization', '/organization', 'organization', PeopleAudience24Regular))
  }
  return options
}

function administrationOptions(): ProjectMenuOption[] {
  return [
    menuItem('Users', '/users', 'users', People24Regular),
    menuItem('Settings', '/settings', 'settings', Settings24Regular)
  ]
}

function projectItems(projects: ProjectRegistryItem[]): ProjectMenuOption[] {
  return [
    menuItem('Home', '/compdocs/home', 'compdocsHome', Home24Regular),
    menuItem('Doc Analyzer', '/compdocs/docAnalyzer', 'docAnalyzer', EyeTracking24Regular),
    menuItem(
      'Cover Page Creator',
      '/compdocs/coverpagecreator',
      'coverpagecreator',
      Document24Regular
    ),
    { key: 'divider2', type: 'divider', name: 'projectDivider' },
    ...projects.map(projectMenuItem)
  ]
}

function doorsGroup(): ProjectMenuOption {
  return groupItem('DOORS', '/doors', 'doors', Door20Regular, [
    menuItem('PoC Linker', '/doors/poclinker', 'pocLinker', LinkSquare24Regular),
    menuItem('Agent', '/doors/agent', 'agent', Glasses24Regular),
    menuItem('Script Generator', '/doors/scripter', 'scripter', Edit24Regular)
  ])
}

function developerGroup(): ProjectMenuOption {
  return groupItem('Developer', '/developer', 'developer', Code24Regular, [
    menuItem('DOORS', '/developer/doors', 'developerDoors', Door20Regular)
  ])
}

function compareGroup(): ProjectMenuOption {
  return groupItem('Compare', '/compare', 'compare', ArrowRepeatAll24Regular, [
    menuItem('Excel', '/compare/excel', 'excel', Excel),
    menuItem('Word', '/compare/word', 'word', Word),
    menuItem('Pdf', '/compare/pdf', 'pdf', Pdf)
  ])
}

function groupItem(
  label: string,
  key: string,
  name: string,
  icon: Component,
  children: ProjectMenuOption[]
): ProjectMenuOption {
  return { label, key, name, icon: renderIcon(icon), children }
}

function menuItem(label: string, key: string, name: string, icon: Component): ProjectMenuOption {
  return { label, key, name, icon: renderIcon(icon) }
}

function projectMenuItem(project: ProjectRegistryItem): ProjectMenuOption {
  return {
    label: project.name,
    key: `/compdocs/${project.slug}`,
    name: project.slug,
    disabled: false
  }
}

function renderIcon(iconAsset: Component) {
  return () => h(NIcon, null, { default: () => h(iconAsset) })
}
