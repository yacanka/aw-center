import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../../frontend/node_modules/playwright/index.mjs'

export const root = fileURLToPath(new URL('../../', import.meta.url))
export const output = path.join(root, 'artifacts/aw-center-video')
export const work = path.join(output, '.work')
export const origin = 'http://127.0.0.1:18765'
export const state = path.join(root, '.runtime/aw-center-video/backend')
export const samples = path.join(state, 'examples')
export const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
export const launch = () => chromium.launch({args:['--disable-background-networking','--disable-component-update']})
export const size = {width:1920, height:968}

function pointerLayer() {
  let pointer, ring
  let last = {x:78, y:72}
  const position = (el, x, y) => { el.style.transform = 'translate(' + x + 'px,' + y + 'px)' }
  function install() {
    if (pointer?.isConnected || !document.body) return
    const wrap = document.createElement('div')
    wrap.setAttribute('aria-hidden','true')
    wrap.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;overflow:hidden'
    // Invitation URLs are single-use credentials. The UI still copies and consumes the original value.
    const privacy = document.createElement('style')
    privacy.textContent = '.n-dialog textarea[readonly], .n-modal textarea[readonly] { -webkit-text-security: disc !important; }'
    document.head.appendChild(privacy)
    const shadow = wrap.attachShadow({mode:'closed'})
    shadow.innerHTML = '<style>svg,i{position:absolute;left:0;top:0;pointer-events:none}svg{filter:drop-shadow(0 1px 2px #0008)}i{border:3px solid #128264;border-radius:100%;width:26px;height:26px;opacity:0}</style><i></i><svg width="27" height="34" viewBox="0 0 27 34"><path d="M2 2L23 19L14 20L19 29L14 32L9 22L3 28Z" fill="#192834" stroke="white" stroke-width="2.2" stroke-linejoin="round"/></svg>'
    pointer = shadow.querySelector('svg')
    ring = shadow.querySelector('i')
    document.body.appendChild(wrap)
    position(pointer,last.x-2,last.y-2)
  }
  document.addEventListener('DOMContentLoaded',install)
  document.addEventListener('pointermove', e => {
    last = {x:e.clientX,y:e.clientY}
    install()
    if (pointer) position(pointer,e.clientX-2,e.clientY-2)
  },true)
  document.addEventListener('pointerdown', e => {
    install()
    if (!ring) return
    ring.style.left=(e.clientX-16)+'px'
    ring.style.top=(e.clientY-16)+'px'
    ring.animate([{opacity:.96,scale:'.65'},{opacity:0,scale:'1.6'}],{duration:460})
  },true)
}

export function credentials(role='manager') {
  const {password} = JSON.parse(fs.readFileSync(path.join(state,'access.json')))
  return {username:({manager:'D10001',viewer:'D10002',editor:'D10003'})[role],password}
}

const sessionCookies=new Map()

export async function openSession(browser, role='manager') {
  const context = await browser.newContext({viewport:size,deviceScaleFactor:1,locale:'tr-TR',timezoneId:'Europe/Istanbul',colorScheme:'light',serviceWorkers:'block',acceptDownloads:true})
  const blocked = []
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin === origin || ['data:','blob:','about:'].includes(url.protocol)) return route.continue()
    blocked.push(url.origin)
    await route.abort('blockedbyclient')
  })
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.addInitScript(pointerLayer)
  if (role !== 'public') {
    if(sessionCookies.has(role))await context.addCookies(sessionCookies.get(role))
    const current = await context.request.get(origin+'/api/session/')
    const cookie = (await context.cookies()).find(c=>c.name==='csrftoken')
    if (!current.ok() || !cookie) throw Error('Demo session bootstrap failed')
    if((await current.json()).state!=='authenticated'){
      const auth = await context.request.post(origin+'/api/session/',{data:credentials(role),headers:{'X-CSRFToken':cookie.value,'Origin':origin}})
      if (auth.status()>=300) throw Error('Demo login HTTP '+auth.status())
      sessionCookies.set(role,await context.cookies())
    }
  }
  const page = await context.newPage()
  page.setDefaultTimeout(16000)
  page.setDefaultNavigationTimeout(30000)
  return {context,page,blocked}
}

export function driver(page, log, sceneId) {
  let x=78, y=72
  const start = performance.now()
  const mark = (kind,detail={}) => log.push({kind, seconds:+((performance.now()-start)/1000).toFixed(3),...detail})
  async function move(nx,ny) {
    const ox=x, oy=y
    const frames = Math.max(7, Math.min(19,Math.ceil(Math.hypot(nx-x,ny-y)/50)))
    for(let i=1;i<=frames;i++){
      const t=i/frames, ease=t*t*(3-2*t)
      await page.mouse.move(ox+(nx-ox)*ease,oy+(ny-oy)*ease-9*Math.sin(Math.PI*t))
      await pause(18)
    }
    x=nx; y=ny
  }
  async function target(locator) {
    await locator.waitFor({state:'visible'})
    await locator.scrollIntoViewIfNeeded()
    const box=await locator.boundingBox()
    if(!box) throw Error('Target is not visible')
    // Bounding boxes may be wider than the visible portion of a scrolling table.
    const nx=(Math.max(0,box.x)+Math.min(size.width,box.x+box.width))/2
    const ny=(Math.max(0,box.y)+Math.min(size.height,box.y+box.height))/2
    await move(nx,ny)
    return {x:nx-box.x,y:ny-box.y}
  }
  const d = {
    page, samples, pause, mark, credentials,
    async go(url) {
      if (!url.startsWith('/app/') || url.startsWith('//')) throw Error('Only demo SPA routes are allowed')
      await page.goto(origin+url,{waitUntil:'domcontentloaded'})
      await page.locator('#app > *').first().waitFor({state:'attached'})
      await page.evaluate(()=>document.fonts.ready)
      mark('sayfa_açıldı',{route:new URL(page.url()).pathname})
    },
    async scroll(loc) {
      await loc.evaluate(el=>el.scrollIntoView({behavior:'smooth', block:'center',inline:'nearest'}))
      await pause(450)
      await loc.waitFor({state:'visible'})
      mark('kaydırıldı')
    },
    async hover(loc) {await target(loc); await pause(180); mark('üzerine_gelindi')},
    async click(loc) {
      await loc.click({trial:true,timeout:16000})
      const position=await target(loc)
      await pause(120)
      await loc.click({position,timeout:12000})
      mark('tıklandı')
      await pause(180)
    },
    async fill(loc,value) {
      await d.click(loc)
      await loc.press('ControlOrMeta+a')
      if(value.length>42 || await loc.getAttribute('type')==='password') await loc.fill(value)
      else await loc.pressSequentially(value,{delay:40})
      mark('alan_dolduruldu')
    },
    async file(loc,filename) {
      const files = Array.isArray(filename)?filename:[filename]
      if(files.some(f=>!path.resolve(f).startsWith(samples+path.sep)))throw Error('Only generated demo fixtures can be uploaded')
      const wrapper=loc.locator('xpath=..')
      if(await wrapper.isVisible()) await target(wrapper)
      await loc.setInputFiles(filename)
      mark('dosya_seçildi',{files:files.map(f=>path.basename(f))})
      await pause(420)
    },
    async download(action) {
      const [result]=await Promise.all([page.waitForEvent('download',{timeout:16000}),action()])
      const name=path.basename(result.suggestedFilename())
      const dir=path.join(work,'downloads',sceneId)
      fs.mkdirSync(dir,{recursive:true})
      await result.saveAs(path.join(dir,name))
      if(!fs.statSync(path.join(dir,name)).size)throw Error('Empty download')
      mark('dosya_indirildi',{file:name})
      return path.join(dir,name)
    }
  }
  return d
}
