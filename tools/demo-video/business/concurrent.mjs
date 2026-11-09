import {openSession,origin} from '../driver.mjs'
import {project,beat,search,enterRow,drawer,modal,clickButton,input,seen,gone} from './helpers.mjs'

const number='ATL-DOK-014'
const api=origin+'/api/projects/gokbey/compliance-documents/'

async function changeFromEditor(page) {
  const {context}=await openSession(page.context().browser(),'editor')
  try {
    const list=await context.request.get(api,{params:{search:number}})
    const document=(await list.json()).results.find(row=>row.number===number)
    const csrf=(await context.cookies(origin)).find(cookie=>cookie.name==='csrftoken')
    const revised=await context.request.patch(api+document.id+'/',{
      headers:{Origin:origin,'X-CSRFToken':csrf.value},
      data:{version:document.version,name:'Atlas teslim denetimi · sürüm '+(document.version+1)}
    })
    if(!revised.ok() || (await revised.json()).version!==document.version+1)
      throw Error('The second editor could not commit the expected version.')
  } finally {
    await context.close()
    await page.bringToFront()
  }
}

export const concurrent={id:'compliance-conflict',title:'İki kişinin aynı belgeyi düzenlemesi',route:project,beats:[
  beat('Açık formdaki taslak','Belge adını düzenlerken başka bir ekip üyesi aynı kaydı güncelliyor. İki oturum aynı sürümden başladı.',async d=>{
    await search(d,number)
    await enterRow(d,number)
    await clickButton(d,'Full details',drawer(d))
    await clickButton(d,'Edit compliance document',modal(d))
    const name=input(modal(d),'Name')
    d.conflictDraft=(await name.inputValue()).endsWith('B')?'Atlas teslim denetimi · A':'Atlas teslim denetimi · B'
    await d.fill(name,d.conflictDraft)
    await changeFromEditor(d.page)
  }),
  beat('Sürüm çakışması penceresi','Kaydettiğimizde uygulama sürüm çakışmasını bildiriyor. Taslağı koruma ve güncel sürümü yükleme seçenekleri var.',async d=>{
    await clickButton(d,'Update',modal(d))
    await seen(d.page.getByText('Document changed',{exact:true}))
  }),
  beat('Taslağı koruyarak çözüm','Güncel sürümü karşılaştırma için yüklüyoruz. Düzenlediğimiz başlığı kontrol edip yeni sürüm üzerine kaydediyoruz.',async d=>{
    await clickButton(d,'Reload and compare',d.page.locator('.n-dialog'))
    const name=input(modal(d),'Name')
    if(await name.inputValue()!==d.conflictDraft) throw Error('The editor draft was lost on reload.')
    await clickButton(d,'Update',modal(d))
    await gone(modal(d))
    if(await drawer(d).isVisible()) await d.click(drawer(d).locator('.n-drawer-header__close'))
    await seen(d.page.getByText(d.conflictDraft,{exact:true}))
  })
]}
