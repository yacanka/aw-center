import {origin} from '../driver.mjs'
import {beat,ensureJira,clickButton,btn,file,choose,seen,txt,drawer,input} from './helpers.mjs'

const card=d=>drawer(d).locator('.n-card').filter({has:txt(d.page,'JIRA review bridge')}).last()

export const analysisDraft={
  id:'job-jira-draft',title:'Analiz bulgularını JIRA görevine dönüştürme',route:'/app/jira',simulated:true,
  async ready(d) {
    await ensureJira(d)
    await d.go('/app/compdocs/docAnalyzer')
    await file(d,'atlas.docx')
    await clickButton(d,'Queue private analysis')
    await btn(d.page,'Download result').waitFor({timeout:45000})
  },
  beats:[
    beat('İş ayrıntısından JIRA taslağı','Belge analizinin ayrıntılarını açıyoruz. Puan özeti altında Atlas projesini seçince rapordaki bulgulardan bir JIRA görevi hazırlanıyor.',async d=>{
      await clickButton(d,'Show in Job Center')
      await seen(txt(drawer(d),'Document analysis summary'))
      const panel=card(d)
      await seen(panel)
      const select=panel.locator('.n-select')
      if(!(await select.innerText()).includes('Atlas Demo')){
        await choose(d,select,/Atlas Demo/)
        await d.page.keyboard.press('Escape')
      }
      await clickButton(d,'Prepare JIRA draft',panel)
      await seen(input(panel,'Summary'))
      await d.scroll(input(panel,'Summary'))
    }),
    beat('Bulguları inceleyip görevi düzenleme','Özet alanına ekip için takip edilecek konuyu yazıyoruz. Açıklamada hangi belgenin ve hangi kontrollerin bu göreve kaynak olduğu görülüyor.',async d=>{
      const panel=card(d)
      await d.fill(input(panel,'JIRA project key'),'DEMO')
      await d.fill(input(panel,'Summary'),'Atlas teslim belgesinin bulgularını incele')
      const findings=input(panel,'Explainable findings')
      if(!(await findings.inputValue()).includes('atlas.docx')) throw Error('The draft does not cite its source document.')
      await clickButton(d,'Save draft',panel)
      await seen(d.page.getByRole('button',{name:'Save draft',disabled:true,exact:true}))
      await d.scroll(findings)
    }),
    beat('Yayın öncesi denetim ve onay','Taslağın bu sürümünü onaylıyoruz. Bağlantı ve zorunlu JIRA alanları doğrulandıktan sonra yayın düğmesi etkinleşiyor.',async d=>{
      const panel=card(d)
      await clickButton(d,'Approve current version',panel)
      const check=btn(panel,'Check connection and requirements')
      await d.scroll(check)
      const [result]=await Promise.all([
        d.page.waitForResponse(r=>r.url().includes('/issue-drafts/') && r.url().endsWith('/preflight/'),{timeout:45000}),
        d.click(check)
      ])
      if(!result.ok() || !(await result.json()).ready) throw Error('The review draft is not ready for publication.')
      const publish=btn(panel,'Publish approved Task')
      await publish.waitFor({timeout:45000})
      await d.scroll(publish)
      if(!await publish.isEnabled()) throw Error('The approved draft is not publishable.')
    }),
    beat('Görev anahtarı ve onay geçmişi','Yayını doğrulayıp sonuç kaydını açıyoruz. İş anahtarı ve taslağın geçmişi kaynak analiz işinin ayrıntılarında birlikte kalıyor.',async d=>{
      const route=new URL(d.page.url())
      await clickButton(d,'Publish approved Task',card(d))
      const [response]=await Promise.all([
        d.page.waitForResponse(r=>r.url().includes('/issue-drafts/') && r.url().endsWith('/publish/') && r.request().method()==='POST'),
        d.click(d.page.locator('.n-popconfirm__action button').last())
      ])
      if(!response.ok()) throw Error('The publication was not accepted.')
      const {id}=await response.json()
      const deadline=Date.now()+45000
      let state
      while(Date.now()<deadline){
        const result=await d.page.context().request.get(origin+'/api/jobs/'+id+'/')
        state=(await result.json()).status
        if(!['queued','running'].includes(state)) break
        await d.pause(500)
      }
      if(state!=='succeeded') throw Error('The JIRA review publication did not finish: '+state)
      await d.go(route.pathname+route.search)
      const panel=card(d)
      const published=panel.locator('.n-alert').filter({hasText:/Published as\s+DEMO-/}).first()
      await published.waitFor({timeout:45000})
      await d.scroll(published)
      await d.click(panel.locator('.n-collapse-item__header').first())
      await seen(panel.locator('.n-timeline-item'))
      await d.scroll(panel.locator('.n-timeline-item').last())
    })
  ]
}
