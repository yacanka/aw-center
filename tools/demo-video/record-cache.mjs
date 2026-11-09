import fs from 'node:fs'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {execFileSync} from 'node:child_process'
import ts from '../../frontend/node_modules/typescript/lib/typescript.js'

const here=import.meta.dirname
const root=path.resolve(here,'../..')
const sha=value=>createHash('sha256').update(value).digest('hex')

function filesIn(relative,include) {
  const directory=path.join(root,relative)
  if(!fs.existsSync(directory))return []
  return fs.readdirSync(directory,{recursive:true,withFileTypes:true})
    .filter(entry=>entry.isFile())
    .map(entry=>path.relative(root,path.join(entry.parentPath,entry.name)))
    .filter(include).sort()
}

function fileKey(files) {
  return sha(JSON.stringify(files.map(file=>[file,sha(fs.readFileSync(path.join(root,file)))])))
}

function helpers(file) {
  const tree=ts.createSourceFile(file,fs.readFileSync(path.join(root,file),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.JS)
  const shared=[], setup=new Map()
  for(const node of tree.statements) {
    if(ts.isFunctionDeclaration(node)||ts.isImportDeclaration(node))shared.push(node.getText())
    if(!ts.isVariableStatement(node))continue
    for(const declaration of node.declarationList.declarations) {
      const value=declaration.initializer
      if(declaration.name.getText()==='scenes')continue
      if(value&&ts.isObjectLiteralExpression(value)&&value.properties.some(p=>p.name?.getText()==='beats'))continue
      if(value&&ts.isCallExpression(value)&&value.arguments.some(a=>ts.isArrayLiteralExpression(a)&&a.elements.some(ts.isCallExpression)))continue
      shared.push(declaration.getText())
    }
  }
  function visit(node) {
    if(ts.isObjectLiteralExpression(node)) {
      const id=node.properties.find(p=>p.name?.getText()==='id')?.initializer
      const ready=node.properties.find(p=>p.name?.getText()==='ready')
      if(id&&ts.isStringLiteral(id)&&ready)setup.set(id.text,ready.getText())
    }
    ts.forEachChild(node,visit)
  }
  visit(tree)
  return {shared:sha(shared.join('\n')),setup}
}

const groupKeys=new Map()
let environmentKey
function dependencies(owner) {
  if(!environmentKey) {
    const ui=/\.(vue|ts|tsx|js|mjs|css|json|svg|woff2?|png|jpg|ico|webp)$/
    const front=filesIn('frontend/src',name=>ui.test(name)&&!/(?:\.test\.|\.spec\.|\/tests\/)/.test(name))
    const assets=filesIn('frontend/public',()=>true)
    const fixtures=filesIn('tools/demo-video/backend_demo',name=>name.endsWith('.py')&&!/\/(?:verify[^/]*|prepare_engineering)\.py$/.test(name))
    environmentKey=fileKey([...front,...assets,...fixtures,'frontend/index.html','frontend/package-lock.json','frontend/vite.config.ts','tools/demo-video/capture.mjs','tools/demo-video/driver.mjs'])
  }
  if(!groupKeys.has(owner)) {
    let modules=[owner],fixtures=[]
    if(owner.includes('/business/')) {
      modules=filesIn('tools/demo-video/business',file=>file.endsWith('.mjs'))
      fixtures=filesIn('tools/demo-video/business',file=>file.endsWith('.py'))
    } else if(owner.endsWith('/supplement.mjs'))fixtures=['tools/demo-video/support_fixtures.py']
    else if(owner.endsWith('/engineering.mjs'))fixtures=['tools/demo-video/backend_demo/prepare_engineering.py']
    else if(owner.endsWith('/admin.mjs'))fixtures=filesIn('tools/demo-video/audio',file=>/recovery|reset/.test(file)&&file.endsWith('.py'))
    const snapshots=modules.map(file=>[file,helpers(file)])
    groupKeys.set(owner,{digest:sha(JSON.stringify([environmentKey,fileKey(fixtures),snapshots.map(([file,h])=>[file,h.shared])])),setup:new Map(snapshots.flatMap(([,h])=>[...h.setup]))})
  }
  return groupKeys.get(owner)
}

// The recording waits for a full beat's voice. Equal-duration editorial changes
// can reuse the picture; the renderer separately fingerprints the audio bytes.
function voiceFrames(file) {
  const fd=fs.openSync(file,'r')
  try {
    const header=Buffer.alloc(44)
    if(fs.readSync(fd,header,0,44,0)!==44||header.toString('ascii',0,4)!=='RIFF'||header.toString('ascii',36,40)!=='data')throw Error('Invalid PCM narration header')
    return Math.ceil(header.readUInt32LE(40)*30/header.readUInt32LE(28))
  } finally {fs.closeSync(fd)}
}

export function captureKey(scene,def,owner) {
  const group=dependencies(owner)
  return sha(JSON.stringify({schema:1, dependencies:group.digest,setup:group.setup.get(scene.id), route:scene.route,role:scene.role||'manager',
    ready:scene.ready?.toString(),beats:scene.beats.map((beat,i)=>[beat.action.toString(),Boolean(beat.during),voiceFrames(def.beats[i].wav)])}))
}

function cachePath(directory){return path.join(directory,'record-inputs.json')}

export function takeStatus(directory,scene,version,inputs,inspectMedia=false) {
  const meta=path.join(directory,'take.json')
  if(!fs.existsSync(meta))return {reason:'missing metadata'}
  let take,cache
  try {
    take=JSON.parse(fs.readFileSync(meta))
    if(fs.existsSync(cachePath(directory)))cache=JSON.parse(fs.readFileSync(cachePath(directory)))
  } catch{return {reason:'invalid cache metadata'}}
  if(!take.stats||take.scene!==scene.id||take.beats?.length!==scene.beats.length||take.errors?.length||take.blocked?.length)return {reason:'invalid recorded actions'}
  const media=take.stats.file||'take.mp4'
  if(!['take.mkv','take.mp4'].includes(media))return {reason:'invalid media name'}
  const source=path.join(directory,media)
  const size=fs.statSync(source,{throwIfNoEntry:false})?.size
  if(!size)return {reason:'missing media'}
  if(cache) {
    if(cache.inputs!==inputs||cache.media!==media||cache.bytes!==size)return {reason:'recording inputs or media changed'}
  } else if(take.version!==version)return {reason:'legacy scene changed'}
  for(const [i,beat] of take.beats.entries()) {
    if(beat.index!==i||!(beat.end>=beat.ready&&beat.ready>=beat.start))return {reason:'invalid action timing'}
    for(const e of beat.events||[])if(e.kind==='dosya_indirildi') {
      if(!e.file||e.file!==path.basename(e.file))return {reason:'invalid download name'}
      const file=path.join(directory,'..','..','downloads',scene.id,e.file)
      if(!fs.statSync(file,{throwIfNoEntry:false})?.size)return {reason:'missing recorded download'}
    }
  }
  if(inspectMedia) {
    try {
      const args=['-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',source]
      const mediaInfo=JSON.parse(execFileSync('ffprobe',args,{encoding:'utf8'}))
      if(mediaInfo.streams?.[0]?.width!==1920||mediaInfo.streams?.[0]?.height!==968)return {reason:'invalid media geometry'}
    } catch{return {reason:'unreadable media'}}
  }
  return {legacy:!cache,entry:{inputs,media,bytes:size}}
}

export function writeInputs(directory,entry) {
  const dest=cachePath(directory)
  fs.writeFileSync(dest+'.next',JSON.stringify(entry,null,2)+'\n',{mode:0o600})
  fs.renameSync(dest+'.next',dest)
}
