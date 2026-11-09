import {btn,txt,modal,drawer,beat,clickText,seen,gone,clickButton,file,closeModal,choose,ensureJira,jiraTab,resultDownload} from './helpers.mjs'

const jira = (id,title,beats) => ({id,title,route:'/app/jira',simulated:true,beats})
const issueRow=(d,key)=>d.page.locator('tbody tr').filter({has:txt(d.page,key)})
const menuItem=(d,label)=>d.page.getByRole('menuitem',{name:label,exact:true})

export const watcher=jira('jira-watcher','JIRA bağlantısı ve takip listesi',[
  beat('JIRA bağlantı yöntemleri','JIRA oturumu bağlandığında hangi hesapla çalıştığımızı sağ üstten kontrol ediyoruz.',async d=>{
    await ensureJira(d,{showMethods:true})
    await seen(txt(d.page,'JIRA Watcher'))
  }),
  beat('Takibe kayıt ekleme','İş anahtarını girerek belge teslimiyle ilgili kaydı takip listesine ekliyoruz. Proje ve başlık birlikte geliyor.',async d=>{
    await clickButton(d,'Add JIRA issue')
    await d.fill(modal(d).getByRole('textbox'),'DEMO-102')
    await clickButton(d,'Add issue',modal(d))
    await gone(modal(d))
    await seen(issueRow(d,'DEMO-102'))
  }),
  beat('Canlı durum ve alt görev ayrıntısı','Durumu yeniledikten sonra ayrıntı panelinde açık ve tamamlanmış alt görevleri ayrı ayrı inceleyebiliyoruz.',async d=>{
    await clickButton(d,'Sync this page')
    await seen(issueRow(d,'DEMO-102').getByText('İncelemede',{exact:true}))
    await clickButton(d,'Details',issueRow(d,'DEMO-102'))
    await seen(drawer(d).locator('.subtask-list li'))
    const outstanding=drawer(d).getByRole('checkbox',{name:'Outstanding only'})
    if (!await outstanding.isChecked()) await d.click(outstanding)
    await gone(drawer(d).getByText('Sürüm geçmişini doğrula',{exact:true}))
  }),
  beat('Hatırlatma kuyruğu','Yanıtı beklenen alt görevler için kurul numarası ve hedef tarih giriliyor. Bu örnekte bildirim demo kuyruğunda kalıyor.',async d=>{
    await clickButton(d,'Close details',drawer(d))
    await clickButton(d,'Send reminder',issueRow(d,'DEMO-102'))
    await d.fill(modal(d).getByPlaceholder('CCB number'),'12')
    const date=modal(d).locator('.n-date-picker input')
    await d.fill(date,'25.11.2026')
    await date.press('Tab')
    await clickButton(d,'Queue reminder',modal(d))
    await seen(d.page.getByText(/Reminder queued for DEMO-102/))
  }),
  beat('Bileşene göre ayrıntı ayarları','Bileşen için hangi ayrıntıların görüneceğini belirleyebiliyoruz. Seçim kullanıcı tercihine kaydediliyor.',async d=>{
    await clickButton(d,'Watcher settings')
    const panel=modal(d)
    const available=panel.getByText(/Available fields loaded/)
    if (!await available.isVisible()) {
      await choose(d,panel.locator('.n-select').first(),/Atlas Demo/)
    }
    await seen(available)
    await clickButton(d,'Save detail fields',panel)
    await seen(txt(panel,'Detail fields saved for this component.'))
  }),
  beat('Takip kaydını kaldırma','Artık izlemeyeceğimiz işi takip listesinden kaldırıyoruz. Onay sonrasında liste güncelleniyor.',async d=>{
    await closeModal(d)
    await clickButton(d,'More actions for DEMO-102',issueRow(d,'DEMO-102'))
    await d.click(menuItem(d,'Remove'))
    await clickButton(d,'Remove',d.page.locator('.n-dialog'))
    await gone(issueRow(d,'DEMO-102'))
  })
])
export const assess=jira('jira-assess','Değişiklik belgesini değerlendirme',[
  beat('ECR dosyası ve etkilenen proje','Değişiklik belgesinin PDF dosyasını seçiyoruz. İncelemeye gidecek alanlar ekranda açıklanıyor.',async d=>{
    await ensureJira(d)
    await clickButton(d,'Assessment')
    await file(d,'ECD-101.pdf',modal(d))
    const select=modal(d).locator('.n-select').first()
    if (!(await select.innerText()).includes('Atlas Demo')) {
      await choose(d,select,/Atlas Demo/)
      await d.page.keyboard.press('Escape')
    }
  }),
  beat('Temsili değerlendirme sonucu','Taslak değerlendirme çıktı olarak görüntüleniyor. Uzman, kararını verirken belgenin kendisini de inceliyor.',async d=>{
    await clickButton(d,'Assess document',modal(d))
    await seen(txt(modal(d),'Assessment result'))
    await d.scroll(modal(d).getByText(/Temsili değerlendirme:/))
  })
])
export const subtasks=jira('jira-subtasks','Kayıtlı listeden ve Excel’den alt görev',[
  beat('Liste ve JIRA alanlarını yükleme','Aynı belgeyi her teslimde gözden geçirecek ekip için tekrar kullanılabilen bir alt görev listesi hazırlıyoruz.',async d=>{
    await jiraTab(d,'Subtask Generator (List)')
    await d.fill(d.page.getByPlaceholder('Enter Url'),'DEMO-101')
    await clickButton(d,'Load Fields')
    await seen(txt(d.page,'Fields Loaded'))
    if (!await d.page.getByPlaceholder('Summary',{exact:true}).nth(1).isVisible()) {
      await clickButton(d,'Add subtask row')
    }
    await d.fill(d.page.getByPlaceholder('Summary',{exact:true}).nth(1),'Teslim dizinini doğrula')
    await d.click(d.page.getByPlaceholder('Enter Url'))
    await clickButton(d,'Save')
    await seen(d.page.getByRole('button',{name:'Save',exact:true,disabled:true}))
  }),
  beat('Alt görev işini başlatma','Listeyi ana işe gönderiyoruz. Durum çubuğu, alt görev oluşturma işleminin sonucunu bildiriyor.',async d=>{
    await clickButton(d,'Generate')
    await d.page.getByText(/Confirmed \d+ JIRA subtasks/).first().waitFor({timeout:45000})
  }),
  beat('Excel sütunu ile görev alanı eşleme','Daha uzun listelerde Excel başlığını JIRA alanına eşliyoruz. Bu dosyada her satırın kısa başlığı ve açıklaması var.',async d=>{
    await jiraTab(d,'Subtask Generator (Excel)')
    await d.fill(d.page.getByPlaceholder('Enter Jira task URL or key'),'DEMO-101')
    await clickButton(d,'Load Fields')
    await seen(d.page.getByText(/subtask fields loaded/i))
    await file(d,'alt-gorevler.xlsx')
    const mappings=d.page.locator('.n-tab-pane:visible .n-select')
    await choose(d,mappings.nth(0),/^Summary/)
    await choose(d,mappings.nth(1),/^Description/)
  }),
  beat('Çalışma kitabından alt görevler','Eşlenen iki satırı aynı ana iş için kuyruğa aldık. Tamamlanma bilgisi işin kendi ilerlemesinden geliyor.',async d=>{
    await clickButton(d,'Generate')
    await d.page.getByText(/Confirmed \d+ JIRA subtasks/).first().waitFor({timeout:45000})
  }),
])
export const dcc=jira('jira-dcc','JIRA kaydından Word belgesi',[
  beat('DCC kaynak görüntüsü','Belgeyi hazırlamadan önce JIRA anahtarını giriyoruz. O andaki alanlardan değişmez bir kayıt alınıyor.',async d=>{
    await jiraTab(d,'DCC Creator')
    await d.fill(d.page.getByPlaceholder('DCC-123 or JIRA browse URL'),'DEMO-101')
    await clickButton(d,'Review immutable snapshot')
    await seen(txt(d.page,'DCC readiness'))
  }),
  beat('Şablon ve eksik alan incelemesi','Hazırlık kontrolü, şablonun işlenip işlenemediğini ve kaynağın ne kadar eksiksiz olduğunu gösteriyor.',async d=>{
    await d.scroll(txt(d.page,'Recommended JIRA fields'))
    const confirm=btn(d.page,'Confirm and queue exact snapshot')
    await seen(confirm)
    if (!await confirm.isEnabled()) await d.click(d.page.locator('.n-tab-pane:visible .n-switch').last())
    await d.scroll(confirm)
  }),
  beat('Onaylanmış Word belgesi','İncelediğimiz sürümü onaylıyoruz. Tamamlandığında Word belgesini aynı iş üzerinden indiriyoruz.',async d=>{
    await clickButton(d,'Confirm and queue exact snapshot')
    await resultDownload(d,'Download verified DOCX')
  })
])
export const ecr={id:'jira-ecr',title:'Değişiklik talebinin yayın onayı',route:'/app/jira',simulated:true,
  ready:async d=>ensureJira(d,{showMethods:true}),beats:[
  beat('ECR inceleme başlatma','Takip ekranından değişiklik talebine geçip PDF dosyasını ve ilgili projeyi seçiyoruz.',async d=>{
    await ensureJira(d)
    await clickButton(d,'Create from ECR')
    await file(d,'ECD-101.pdf')
    const control=d.page.locator('.n-select').filter({hasText:/Select every project/}).first()
    if(await control.count()) {
      await choose(d,control,/Atlas Demo/)
      await d.page.keyboard.press('Escape')
    }
    await seen(btn(d.page,'Review PDF snapshot'))
  }),
  beat('PDF içeriğini inceleme','PDF içindeki talep numarası, belge adı ve gerekçe inceleme kaydına alınıyor. Onaydan önce kaynak içeriği görebiliyoruz.',async d=>{
    await clickButton(d,'Review PDF snapshot')
    await seen(txt(d.page,'Approval plan'))
    await d.scroll(d.page.locator('.n-descriptions').first())
  }),
  beat('Yayın planı ve ön kontrol','Yayınlanacak JIRA projesini belirleyip bağlantı ve zorunlu alanları kontrol ediyoruz.',async d=>{
    await d.fill(d.page.getByPlaceholder('AWC'),'DEMO')
    await clickButton(d,'Add subtask')
    await d.fill(d.page.locator('.subtask-card input').first(),'Yeni dizini gözden geçir')
    await clickButton(d,'Check connection and requirements')
    await seen(d.page.getByText(/ready for safe publication/))
  }),
  beat('Onay ve temsili yayın','Plan onaylandıktan sonra yayın için ayrıca onay veriliyor. Örnek işlemin sonucu ve iş anahtarı kayda bağlanıyor.',async d=>{
    await clickButton(d,'Approve publication plan')
    await clickButton(d,'Publish approved ECR')
    await d.click(d.page.locator('.n-popconfirm__action button').last())
    const published=d.page.getByText(/Published as DEMO-/)
    await published.waitFor({timeout:45000})
    await d.scroll(published)
  }),
  beat('İkinci talebi reddetme','Ayrı bir incelemeyi reddediyoruz. Ret kararı geçmişte görünür ve bu talep için yayın düğmesi kapanır.',async d=>{
    await file(d,'ECD-101.pdf')
    await clickButton(d,'Review PDF snapshot')
    await clickButton(d,'Reject review')
    await d.click(d.page.locator('.n-popconfirm__action button').last())
    const status=d.page.locator('.n-card-header__extra .n-tag').filter({hasText:/^rejected$/}).first()
    await seen(status)
    await gone(btn(d.page,'Publish approved ECR'))
    await d.scroll(status)
  }),
]}

export const listTools=jira('jira-lists','Kişisel alt görev şablonları',[
  beat('Liste sekmesi ve adlandırma','Tekrarlanan kontroller için ayrı bir liste açıp ekibin tanıyacağı bir ad veriyoruz.',async d=>{
    await jiraTab(d,'Subtask Generator (List)')
    const lists=d.page.locator('.subtask-tools').first()
    await seen(lists)
    await d.click(d.page.locator('.n-tabs-tab--addable:visible').last())
    const selected=d.page.locator('.n-tabs-tab--active:visible').filter({hasText:'New List'}).last()
    const name=selected.getByText('New List',{exact:true}).first()
    await d.hover(name)
    await name.dblclick()
    const field=d.page.locator('.n-tabs-tab--active:visible input:visible').last()
    await d.fill(field,'Teslim kontrolleri')
    await field.press('Enter')
    await seen(txt(d.page,'Teslim kontrolleri'))
  }),
  beat('Dinamik sütun ve toplu değer','JIRA alanlarını yüklüyor ve açıklama sütununu listeye ekliyoruz. Ortak değeri seçilen satırlara bir kerede yazıyoruz.',async d=>{
    await d.fill(d.page.getByPlaceholder('Enter Url'),'DEMO-101')
    await clickButton(d,'Load Fields')
    await seen(txt(d.page,'Fields Loaded'))
    const pane=d.page.locator('.n-tab-pane:visible').filter({has:d.page.locator('.subtask-tools')}).last()
    const choices=pane.locator('.subtask-tools > .n-select')
    await d.click(choices)
    const description=d.page.locator('.n-base-select-option:visible').filter({hasText:'Description'}).first()
    if(!(await description.getAttribute('class')).includes('selected')) await d.click(description)
    await d.page.keyboard.press('Escape')
    if (!await pane.getByPlaceholder('Summary',{exact:true}).nth(1).isVisible()) await clickButton(d,'Add subtask row',pane)
    await d.fill(pane.getByPlaceholder('Summary',{exact:true}).first(),'Dosya teslimini incele')
    await d.fill(pane.getByPlaceholder('Description',{exact:true}).first(),'Revizyon numarasını kontrol et.')
    await clickButton(d,'Set Values',pane)
    await clickButton(d,'Save')
    await seen(d.page.getByRole('button',{name:'Save',disabled:true,exact:true}))
  }),
  beat('Kullanılmayan listeyi kaldırma','Kaldırılan sekme kaydedildiğinde kişisel liste koleksiyonundan da çıkıyor. Bu değişiklik ana JIRA işine dokunmuyor.',async d=>{
    const entry=d.page.locator('.n-tabs-tab').filter({has:txt(d.page,'Teslim kontrolleri')})
    await d.click(entry.getByRole('button',{name:'close'}).last())
    await gone(txt(d.page,'Teslim kontrolleri'))
    await clickButton(d,'Save')
    await seen(d.page.getByRole('button',{name:'Save',disabled:true,exact:true}))
  })
])
