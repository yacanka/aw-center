import {dashboard,register,workspace,archive,imports,settings,outputs,viewer,analysis,covers,doors,numbering,tableTools,decisions} from './compliance.mjs'
import {watcher,assess,subtasks,dcc,ecr,listTools} from './jira.mjs'
import {concurrent} from './concurrent.mjs'
import {analysisDraft} from './analysis_draft.mjs'
import {ecrRecovery,interrupted} from './recovery.mjs'
import {execFileSync} from 'node:child_process'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
const base=fileURLToPath(new URL('../../../',import.meta.url))
const fixtureScenes=new Set(['compliance-decisions','compliance-numbering','compliance-archive','compliance-register','compliance-import','compliance-workflow','compliance-settings','jira-watcher','jira-subtasks','jira-lists','document-analysis'])
export const scenes=[dashboard,register,concurrent,workspace,decisions,archive,imports,settings,outputs,doors,numbering,tableTools,viewer,analysis,analysisDraft,covers,watcher,assess,subtasks,listTools,dcc,ecr,ecrRecovery,interrupted].map(scene=>fixtureScenes.has(scene.id) ? {...scene,ready:async d=>{
  execFileSync(path.join(base,'.venv/bin/python'),[path.join(base,'tools/demo-video/business/prepare_scene.py'),scene.id],{env:{...process.env,AW_VIDEO_DEMO:'1'}})
  await d.go(scene.route)
  await d.page.locator('main').first().waitFor({state:'visible',timeout:20000})
  await d.page.waitForFunction(()=>Array.from(document.querySelectorAll('main')).some(el=>el.innerText.trim().length>50),{},{timeout:20000})
}} : scene)
