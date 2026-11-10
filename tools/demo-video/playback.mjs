import fs from 'node:fs'
import path from 'node:path'
import {pathToFileURL} from 'node:url'
import {launch,work,output} from './driver.mjs'
const pilot=process.argv.includes('--pilot')
const folder=pilot?path.join(work,'pilot'):output
const video=path.join(folder,pilot?'pilot.mp4':'AW_Center_Tanitim_TR.mp4')
const manifest=JSON.parse(fs.readFileSync(path.join(folder,'scenes.json')))
const browser=await launch()
try {
  const page=await browser.newPage({viewport:{width:1280,height:720}})
  await page.goto(pathToFileURL(video).href,{waitUntil:'domcontentloaded'})
  const element=page.locator('video')
  await element.waitFor()
  const results=[]
  for(const scene of manifest){
    const action=scene.beats.flatMap(b=>b.timing.events).find(e=>['tıklandı','dosya_seçildi','alan_dolduruldu','üzerine_gelindi'].includes(e.kind)&&typeof e.finalSeconds==='number')
    const outcome=scene.beats.at(-1)
    const marks=[
      ['giriş',scene.start+.2],
      ['etkileşim',action?.finalSeconds??scene.beats[0].finalActionStart+.5],
      ['sonuç',Math.max(outcome.finalStart,scene.start+outcome.timing.ready)+.12]
    ]
    const samples=[]
    for(const [kind,when] of marks) {
      const timestamp=Math.max(scene.start,Math.min(when,scene.end-.8))
      const data=await element.evaluate(async(el,t)=>{
      const deadline = new Promise((_,reject)=>setTimeout(()=>reject(Error('Playback timeout')),7000))
      return await Promise.race([deadline,(async()=>{
        el.currentTime=t
        if(el.seeking)await new Promise(r=>el.addEventListener('seeked',r,{once:true}))
        const before=el.currentTime
        // A muted player can start without a user gesture. Audio is measured separately.
        el.muted=true
        await el.play()
        await new Promise(r=>setTimeout(r,550))
        el.pause()
        return {before,after:el.currentTime,width:el.videoWidth,height:el.videoHeight,ready:el.readyState}
      })()])
      },timestamp)
      if(data.width!==1920 || data.height!==1080 || data.after<=data.before)throw Error('Playback did not advance: '+scene.id+' '+kind)
      samples.push({kind,...data})
    }
    results.push({id:scene.id,...samples[0],samples})
  }
  fs.writeFileSync(path.join(work,pilot?'pilot-playback.json':'playback.json'),JSON.stringify(results,null,2))
  console.log('Chromium decoded and played',results.length,'chapters at',results.length*3,'positions')
}finally{await browser.close()}
