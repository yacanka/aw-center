// Chromium compositor JPEGs are stored directly as time-coded Matroska packets.
// A 30 Hz sampling clock records real movement without recompressing unchanged UI.
import fs from 'node:fs'
import {once} from 'node:events'
import {performance} from 'node:perf_hooks'
import {size,pause} from './driver.mjs'

const id = hex => Buffer.from(hex,'hex')
function vint(n) {
  const bytes=Math.max(1,Math.ceil(Math.log2(n+2)/7))
  const buffer=Buffer.alloc(bytes)
  buffer.writeUIntBE(n,0,bytes)
  buffer[0]|=1<<(8-bytes)
  return buffer
}
function element(tag,...data) {
  const body=Buffer.concat(data)
  return Buffer.concat([id(tag),vint(body.length),body])
}
function uint(tag,value) {
  const bytes=Math.max(1,Math.ceil(Math.log2(value+1)/8))
  const data=Buffer.alloc(bytes)
  data.writeUIntBE(value,0,bytes)
  return element(tag,data)
}
const str=(tag,value)=>element(tag,Buffer.from(value))
const unknown=Buffer.from([0x01,255,255,255,255,255,255,255])
function header() {
  const ebml=element('1A45DFA3',uint('4286',1),uint('42F7',1),uint('42F2',4),uint('42F3',8),str('4282','matroska'),uint('4287',4),uint('4285',2))
  const info=element('1549A966',uint('2AD7B1',1000000),str('4D80','AW Center Demo'),str('5741','Chromium compositor'))
  const track=element('AE',uint('D7',1),uint('73C5',1),uint('83',1),uint('9C',0),str('86','V_MJPEG'),uint('23E383',33333333),element('E0',uint('B0',size.width),uint('BA',size.height)))
  return Buffer.concat([ebml,id('18538067'),unknown,info,element('1654AE6B',track)])
}
export async function startCapture(page, filename) {
  const session=await page.context().newCDPSession(page)
  const stream=fs.createWriteStream(filename)
  let latest,changed=0,packets=0,lastImage,cluster=-1,previous=-1,first,last
  let failure
  stream.on('error',e=>{failure=e})
  stream.write(header())
  session.on('Page.screencastFrame',frame=>{
    latest=Buffer.from(frame.data,'base64')
    changed++
    first??=frame.metadata.timestamp
    last=frame.metadata.timestamp
    session.send('Page.screencastFrameAck',{sessionId:frame.sessionId}).catch(()=>{})
  })
  await session.send('Page.startScreencast',{format:'jpeg',quality:94,maxWidth:size.width,maxHeight:size.height,everyNthFrame:1})
  const limit=performance.now()+9000
  while(!latest && performance.now()<limit)await pause(20)
  if(!latest){stream.end();throw Error('No Chromium compositor frame')}
  const start=performance.now()
  const frameIndex=()=>Math.floor((performance.now()-start)*.03)
  function write(frame,force=false){
    if(frame===previous || (!force && latest===lastImage))return
    const timestamp=Math.round(frame*1000/30)
    if(cluster<0 || timestamp-cluster>=12000){
      cluster=timestamp
      stream.write(Buffer.concat([id('1F43B675'),unknown,uint('E7',cluster)]))
    }
    const block=Buffer.from([0x81,0,0,0x80])
    block.writeInt16BE(timestamp-cluster,1)
    stream.write(Buffer.concat([id('A3'),vint(latest.length+4),block]))
    stream.write(latest)
    previous=frame
    lastImage=latest
    packets++
  }
  write(0,true)
  const timer=setInterval(()=>write(frameIndex()),10)
  return {start,async stop(){
    clearInterval(timer)
    const lastFrame=frameIndex()
    write(lastFrame,true)
    await session.send('Page.stopScreencast').catch(()=>{})
    await session.detach().catch(()=>{})
    const closed=once(stream,'close')
    stream.end()
    await closed
    if(failure)throw failure
    return {file:'take.mkv',frames:lastFrame+1,changedFrames:changed,packets,nativeSpan:last-first,duration:(lastFrame+1)/30}
  }}
}
