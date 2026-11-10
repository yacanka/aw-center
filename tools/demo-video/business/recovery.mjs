import {execFileSync} from 'node:child_process'
import path from 'node:path'
import {root} from '../driver.mjs'
import {beat,ensureJira,clickButton,btn,seen,gone,project,modal,txt,input,clickText,jiraTab,search,enterRow,drawer} from './helpers.mjs'

function pauseProvider(system,state){
  return execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'tools/demo-video/business/provider_pause.py'),system,state],
    {env:{...process.env,AW_VIDEO_DEMO:'1'},encoding:'utf8'}).trim()
}

function fixture(action,job) {
  const script=path.join(root,'tools/demo-video/business/ecr_recovery.py')
  const args=job?[script,action,job]:[script,action]
  const data=execFileSync(path.join(root,'.venv/bin/python'),args,{env:{...process.env,AW_VIDEO_DEMO:'1'},encoding:'utf8'})
  return JSON.parse(data.trim().split('\n').at(-1))
}

export const ecrRecovery={
  id:'jira-recovery',title:'Yayını durdurma ve JIRA durumunu uzlaştırma',route:'/app/jira',simulated:true,
  async ready(d){
    await ensureJira(d)
    d.recovery=fixture('stage')
    await d.go('/app/task/ecr?ecr_workflow='+d.recovery.workflow)
    await seen(btn(d.page,'Cancel publication'))
  },
  beats:[
    beat('Devam eden ECR yayınının iptali','Yayın sürerken iptal istiyoruz. Örnekte JIRA kaydı işlediği hâlde önceki isteğe yanıt ulaşmamış.',async d=>{
      await clickButton(d,'Cancel publication')
      await seen(d.page.getByText('Publication cancellation requested.',{exact:true}))
      fixture('cancel',d.recovery.job)
      const message=d.page.getByText(/previous external write has an uncertain outcome/)
      await message.waitFor({timeout:30000})
      await d.scroll(message)
    }),
    beat('Yazma sonucunu doğrulama','Uzlaştırmayı başlatınca uygulama mevcut işin ve PDF ekinin izini doğruluyor. Tek bir iş anahtarıyla yayın kapanıyor.',async d=>{
      await clickButton(d,'Resume publication')
      await d.click(d.page.locator('.n-popconfirm__action button').last())
      const published=d.page.getByText('Published as '+d.recovery.issue,{exact:false}).first()
      await published.waitFor({timeout:45000})
      await d.scroll(published)
    })
  ]
}

export const interrupted={
  id:'provider-retry',title:'Kesintiye uğrayan alt görev ve numara ataması',route:'/app/jira',simulated:true,
  async ready(d){
    execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'tools/demo-video/business/prepare_scene.py'),'jira-subtasks'],
      {env:{...process.env,AW_VIDEO_DEMO:'1'}})
    await jiraTab(d,'Subtask Generator (List)')
    await d.fill(d.page.getByPlaceholder('Enter Url'),'DEMO-101')
    await clickButton(d,'Load Fields')
    await seen(txt(d.page,'Fields Loaded'))
    if (!await d.page.getByPlaceholder('Summary',{exact:true}).nth(1).isVisible()) await clickButton(d,'Add subtask row')
    await d.fill(d.page.getByPlaceholder('Summary',{exact:true}).nth(1),'Karar listesini doğrula')
    await d.click(d.page.getByPlaceholder('Enter Url'))
  },
  beats:[
    beat('Belirsiz alt görev sonucu','Bu örnekte alt görev gönderilirken bağlantı kesiliyor. Aynı listeyi tekrar çalıştırınca önceki paketin durumu karşımıza çıkıyor.',async d=>{
      pauseProvider('jira','hold')
      try {
        await clickButton(d,'Generate')
        await d.page.getByText(/JIRA may have created subtask/).first().waitFor({timeout:40000})
      } finally {
        pauseProvider('jira','release')
      }
      await clickButton(d,'Generate')
      await seen(txt(d.page,'Previous subtask batch'))
    }),
    beat('Önceki alt görev paketine devam','Önceki paketi seçiyoruz. JIRA kayıtları kontrol ediliyor ve tamamlanan alt görev sayısı bildiriliyor.',async d=>{
      await clickButton(d,'Resume previous batch',d.page.locator('.n-dialog'))
      await d.page.getByText(/Confirmed \d+ JIRA subtasks/).first().waitFor({timeout:45000})
    }),
    beat('Numara kullanım onayında kesinti','Bir başka örnekte kapak numarası alınmış ancak kullanım onayı kesilmiş. Formda bu atama için tekrar deneme seçeneği çıkıyor.',async d=>{
      await d.go(project)
      await clickButton(d,'New')
      await clickText(d,modal(d),'Create with Numarator')
      await d.fill(input(modal(d),'Name'),'Yayın kontrol listesi')
      await d.fill(modal(d).getByLabel('seri',{exact:false}).and(d.page.locator('input')),'ATL')
      d.resumedNumber=pauseProvider('number','hold')
      try {
        await clickButton(d,'Get number from Numarator',modal(d))
        await btn(modal(d),'Retry').waitFor({timeout:45000})
        await d.scroll(btn(modal(d),'Retry'))
      } finally {
        pauseProvider('number','release')
      }
    }),
    beat('Aynı kapak numarasıyla tamamlama','Yeniden denediğimizde işlem aynı numarayla tamamlanıyor. Atanan numarayı belgenin çalışma alanında kontrol ediyoruz.',async d=>{
      await clickButton(d,'Retry',modal(d))
      await gone(modal(d))
      await search(d,d.resumedNumber)
      await enterRow(d,'Yayın kontrol listesi')
      await seen(drawer(d).getByText(d.resumedNumber,{exact:false}).first())
    })
  ]
}
