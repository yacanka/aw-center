import fs from 'node:fs'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {execFileSync} from 'node:child_process'
import {launch,openSession,driver,work,pause,root} from './driver.mjs'
import {startCapture} from './capture.mjs'

const [command='list',...args]=process.argv.slice(2)
const hash=s=>createHash('sha256').update(s).digest('hex').slice(0,16)
const owners=new WeakMap()
async function optional(relative) {
  if(!fs.existsSync(new URL(relative,import.meta.url)))return []
  const {scenes}=await import(relative)
  for(const scene of scenes)owners.set(scene,'tools/demo-video/'+relative.slice(2))
  return scenes
}
const scenes=[...await optional('./tour.mjs'),...await optional('./business/scenes.mjs'),...await optional('./extra.mjs'),...await optional('./admin.mjs'),...await optional('./engineering.mjs'),...await optional('./supplement.mjs')]
const voiceDir=path.join(work,'speech')
const takeDir=path.join(work,'takes')
fs.mkdirSync(voiceDir,{recursive:true})
fs.mkdirSync(takeDir,{recursive:true})
const plain=scenes.map(({beats,...scene})=>({...scene,beats:beats.map(({action,...beat})=>({...beat,
  wav:path.join(voiceDir,hash(beat.spoken||beat.text)+'.wav')}))}))
if(command==='list'){await new Promise((resolve,reject)=>process.stdout.write(JSON.stringify(plain,null,2)+'\n',err=>err?reject(err):resolve()));process.exit(0)}
const selected=scenes.filter(s=>!args.length||args.includes(s.id))
if(command!=='inspect'&&!selected.length) throw Error('No matching scenes')
function versionOf(scene,def){
  return hash(JSON.stringify(def)+scene.beats.map(b=>b.action.toString()).join(''))
}
const {captureKey,takeStatus,writeInputs}=await import('./record-cache.mjs')
if(command==='audit'||command==='bootstrap-cache'){
  const problems=[],pending=[]
  for(const scene of selected){
    const directory=path.join(takeDir,scene.id)
    const def=plain.find(s=>s.id===scene.id)
    if(def.beats.some(beat=>!fs.existsSync(beat.wav))){problems.push(scene.id+': missing narration');continue}
    const inputs=captureKey(scene,def,owners.get(scene))
    const status=takeStatus(directory,scene,versionOf(scene,def),inputs,command==='bootstrap-cache')
    if(status.reason)problems.push(scene.id+': '+status.reason)
    else if(status.legacy)pending.push([directory,status.entry])
  }
  if(problems.length){console.error(problems.join('\n'));process.exit(1)}
  if(command==='bootstrap-cache'){
    for(const [directory,entry] of pending)writeInputs(directory,entry)
    console.log('Validated legacy inputs written:',pending.length)
  }else console.log('Validated recordings:',selected.length,'; eligible legacy takes:',pending.length)
  process.exit(0)
}
function safeSnapshot(snapshot){
  return snapshot.split('\n').map(line=>line
    .replace(/((?:textbox|searchbox|spinbutton)(?: "[^"]*")?(?: \[[^\]]*\])*)\s*:.*$/i,'$1')
    .replace(/(?:https?:\/\/[^\s"<>]+)?\/app\/(?:invite|login)[?#][^\s"<>]+/gi,'[redacted link]')
    .replace(/\b(?:JSESSIONID|sessionid|csrftoken|authorization|access_token|refresh_token|download_token|api_token)\s*[:=]\s*["']?(?:bearer\s+)?[A-Za-z0-9_./+=-]{12,}/gi,'[redacted credential]')).join('\n')
}
const browser=await launch()
try{
  if(command==='inspect'){
    const {context,page}=await openSession(browser,process.env.AW_INSPECT_ROLE||'manager')
    try{for(const route of args){
      await driver(page,[],'inspection').go(route)
      await pause(700)
      console.log('\n'+new URL(route,'http://localhost').pathname+'\n'+safeSnapshot(await page.locator('body').ariaSnapshot()))
    }}finally{await context.close()}
  }else{
    const failed=[]
    for(const scene of selected){
      const dir=path.join(takeDir,scene.id)
      const meta=path.join(dir,'take.json')
      const def=plain.find(s=>s.id===scene.id)
      const version=versionOf(scene,def)
      const inputs=command==='record'?captureKey(scene,def,owners.get(scene)):null
      if(command==='record'&&!process.env.AW_RESHOOT&&!takeStatus(dir,scene,version,inputs).reason)continue
      fs.mkdirSync(dir,{recursive:true})
      console.log('Scene',scene.id)
      const {context,page,blocked}=await openSession(browser,scene.role||'manager')
      const log=[], beats=[], errors=[]
      page.on('pageerror',()=>errors.push('Browser page error'))
      const d=driver(page,log,scene.id)
      let capture,clock,stopped=false
      const now=()=>+(Math.max(0,performance.now()-clock)/1000).toFixed(3)
      try{
        await d.go(scene.route)
        await page.waitForFunction(()=>document.querySelector('#app')?.innerText.trim().length>24)
        await page.evaluate(()=>document.fonts.ready)
        await pause(500)
        if(scene.ready)await scene.ready(d)
        if(command==='record')capture=await startCapture(page,path.join(dir,'pending.mkv'))
        clock=capture?.start||performance.now()
        d.mark('kayıt_başlangıcı')
        const eventOffset=log.at(-1).seconds-now()
        for(const [i,beat] of scene.beats.entries()){
          const audio=def.beats[i].wav
          const duration=command==='record'?Number(execFileSync('ffprobe',['-v','error','-show_entries','format=duration','-of','csv=p=0',audio],{encoding:'utf8'})):0
          const start=now(), from=log.length
          await beat.action(d)
          if(blocked.length)throw Error('Unexpected browser destination: '+blocked.join(','))
          await pause(130)
          d.mark('sonuç_görünüyor')
          const ready=now(),voiceStart=beat.during?start+.08:ready
          if(command==='record')await pause(Math.max(0,(voiceStart+duration+.32-now())*1000))
          await page.screenshot({path:path.join(dir,'b'+i+'.jpg'),type:'jpeg',quality:80,timeout:10000})
          beats.push({index:i,start,ready,voiceStart,voiceDuration:duration,end:now(),events:log.slice(from),actualRoute:new URL(page.url()).pathname})
          console.log('  OK',i+1,beat.feature||beat.text.slice(0,45))
        }
        if(errors.length)throw Error(errors.join('; '))
        if(capture){
          const stats=await capture.stop();stopped=true
          fs.renameSync(path.join(dir,'pending.mkv'),path.join(dir,'take.mkv'))
          fs.writeFileSync(meta,JSON.stringify({version,scene:scene.id,eventClockOffset:eventOffset,stats,beats,blocked,errors},null,2))
          writeInputs(dir,{inputs,media:'take.mkv',bytes:fs.statSync(path.join(dir,'take.mkv')).size})
        }
      }catch(err){
        failed.push(scene.id)
        // Playwright's errors and ARIA values can carry form credentials or URL fragments.
        const failure=err?.name==='TimeoutError'?'TimeoutError':'Recording error'
        const summary=scene.id+' · step '+String(beats.length+1)+' · '+failure
        console.error(summary)
        fs.writeFileSync(path.join(dir,'failure.txt'),summary+'\n',{mode:0o600})
        const privateFields=page.locator('input[type="password"], .n-dialog textarea[readonly], .n-modal textarea[readonly]')
        await page.screenshot({path:path.join(dir,'failure.jpg'),mask:[privateFields]}).catch(()=>{})
      }finally{
        if(capture&&!stopped)await capture.stop().catch(()=>{})
        await context.close()
      }
    }
    if(failed.length){console.error('Failed scenes:',failed.join(' '));process.exitCode=2}
  }
}finally{await browser.close()}
