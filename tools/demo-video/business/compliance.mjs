import {project, title, updatedTitle, btn,txt,modal,drawer,input,beat,clickText,seen,gone,clickButton,file,closeModal,choose,search,enterRow,workspaceRows,drawerTab,resultDownload} from './helpers.mjs'

const D = d => d.page
const searchRow = async (d,term) => {
  await search(d,term)
  await seen(workspaceRows(d).first())
}
export const dashboard = {
  id:'compliance-dashboard', title:'Belge portföyü ve öncelikler', route:'/app/compdocs/home', beats:[
    beat('Proje özet göstergeleri','Atlas projesinde kaç belgenin açık olduğunu, geciken işleri ve risk sinyallerini aynı ekranda görüyoruz.',async d=>{
      const selector=D(d).locator('[aria-label="Compliance dashboard project"]').first()
      await choose(d,selector,/Atlas Demo/)
      await seen(D(d).locator('.metrics .n-statistic'))
    }),
    beat('Panel ve ATA kırılımı','Panel ve ATA kırılımı, hangi ekibin hangi belgelerden sorumlu olduğunu gösteriyor.',async d=>{
      await d.click(D(d).getByRole('tab',{name:'ATA based'}))
      const row=D(d).locator('.panel-breakdown tbody tr[tabindex]').first()
      await d.click(row)
      await row.press('Enter')
      await seen(D(d).locator('.summary-meta .n-tag'))
      await d.scroll(D(d).locator('.panel-breakdown'))
    }),
    beat('Teslim, kategori ve gerçekleşme grafikleri','Seçili grubun teslim ve kategori dağılımını, planlanan ve gerçekleşen teslimlerle birlikte okuyabiliyoruz.',async d=>{
      await d.scroll(D(d).locator('.dashboard-grid'))
      await seen(D(d).locator('.timeline-surface canvas'))
    }),
    beat('Risk listesinden çalışma alanı','Risk listesinden bir belgeye geçince yöneticinin gördüğü öncelik, ekibin üzerinde çalıştığı kayda bağlanıyor.',async d=>{
      await d.scroll(D(d).locator('.risk-card'))
      await d.click(D(d).locator('.risk-card .priority-header').first())
      await clickButton(d,'Review document')
      await seen(drawer(d).locator('.workspace-title'))
    }),
  ]}
export const register = {id:'compliance-register',title:'Belge listesinden yeni kayda',route:project,beats:[
  beat('Sayfalama ve arama','Tabloda ikinci sayfaya geçebilir veya aradığımız belgeyi listede numarasıyla bulabiliriz.',async d=>{
    await seen(workspaceRows(d))
    await d.click(D(d).locator('.n-pagination-item').filter({hasText:/^2$/}).first())
    await searchRow(d,'ATL-DOK-001')
  }),
  beat('Yeni belge formu','Teslim dizini için belge adı ve kapak numarasını giriyoruz. Bu numara, sonraki güncellemelerde de aynı kaydı tanımlıyor.',async d=>{
    await clickButton(d,'New')
    await d.fill(input(modal(d),'Name'),title)
    await d.fill(input(modal(d),'Cover Page No'),'ATL-KPK-900')
  }),
  beat('Kayıt oluşturma ve tam detay','Kaydı oluşturduğumuzda listede beliriyor. Çalışma alanından tüm alanları ve geçmişi açıyoruz.',async d=>{
    await clickButton(d,'Create',modal(d))
    await gone(modal(d))
    await enterRow(d,title)
    await clickButton(d,'Full details',drawer(d))
    await seen(modal(d).getByText('Identity',{exact:true}))
    await clickText(d,modal(d),'Legacy field history')
  }),
  beat('Kayıt düzenleme','Yeni sürümü adında da belirtiyoruz. Güncellemenin sonucunu doğrudan belge listesinde kontrol edebiliriz.',async d=>{
    await clickButton(d,'Edit compliance document',modal(d))
    await d.fill(input(modal(d),'Name'),updatedTitle)
    await clickButton(d,'Update',modal(d))
    await gone(modal(d))
    if (await drawer(d).isVisible()) await d.click(drawer(d).locator('.n-drawer-header__close'))
    await searchRow(d,'ATL-KPK-900')
    await seen(txt(D(d),updatedTitle))
  })
]}
export const workspace = {id:'compliance-workflow',title:'Sorumluluk, inceleme ve karar geçmişi',route:project,beats:[
  beat('Belge özeti ve bağlamsal yardım','Belgenin paneli, kapak ve teknik belge numarası çalışma alanında birlikte duruyor. Yardım, açık sekmeye göre değişiyor.',async d=>{
    await searchRow(d,'ATL-DOK-011')
    await enterRow(d)
    await clickButton(d,'Help for current workspace tab',drawer(d))
    await seen(D(d).locator('.context-help'))
  }),
  beat('Belge sorumluluğu','Bir sonraki işlemin sahibini seçip atamanın gerekçesini saklıyoruz.',async d=>{
    await drawerTab(d,'Ownership')
    const pane=drawer(d).locator('.n-tab-pane:visible')
    await choose(d,pane.locator('.n-select').first(),/D10001|Deniz/)
    await d.fill(pane.getByPlaceholder('Optional ownership explanation'),'Teslim dosyasının kontrolü')
    await clickButton(d,'Save ownership',pane)
    await seen(txt(D(d),'Document ownership updated.'))
  }),
  beat('İnceleme görevi','Belgeyi bir inceleyiciye atayıp kontrol edeceği noktayı yazıyoruz. İstek, belgenin kendi görev listesine ekleniyor.',async d=>{
    await drawerTab(d,'Review & Approval')
    const pane=drawer(d).locator('.n-tab-pane:visible')
    await choose(d,pane.locator('.n-select').nth(1),/D10001|Deniz/)
    await d.fill(input(pane,'Request note'),'Dizin ve sürüm eşleşmesini doğrula.')
    await clickButton(d,'Create task',pane)
    await seen(txt(pane,'Dizin ve sürüm eşleşmesini doğrula.'))
  }),
  beat('İnceleme kararı','İnceleyici kararını bir notla kaydediyor. Onaylanan görev listede durumuyla kalıyor.',async d=>{
    const card=drawer(d).locator('.n-card').filter({has:txt(D(d),'Dizin ve sürüm eşleşmesini doğrula.')}).first()
    await d.fill(card.getByPlaceholder('Decision note'),'Dizin ve sürüm eşleşiyor.')
    await clickButton(d,'Approve', card)
    await seen(txt(drawer(d),'approved'))
  }),
  beat('Durum geçişi ve işlem geçmişi','Belgenin durum geçişine gerekçe ekliyoruz. İşlem geçmişi, atamayı ve kararı daha sonra izlememizi sağlıyor.',async d=>{
    await drawerTab(d,'Transition')
    const pane=drawer(d).locator('.n-tab-pane:visible')
    await choose(d,pane.locator('.n-select').first())
    await d.fill(pane.getByPlaceholder('Optional transition explanation'),'Dizin incelemesi tamamlandı.')
    await clickButton(d,'Save transition',pane)
    await seen(txt(D(d),'Lifecycle transition recorded.'))
    await drawerTab(d,'Activity')
    await seen(drawer(d).locator('.n-timeline-item'))
  }),
  beat('Belge takibi ve bildirim politikası','Belge bazında uyarıları, proje düzeyinde ise ortak bildirim politikasını yönetebiliyoruz.',async d=>{
    await drawerTab(d,'Tracking & Alerts')
    const pane=drawer(d).locator('.n-tab-pane:visible')
    await seen(txt(pane,'DocProof revision'))
    await d.click(pane.locator('.n-switch').first())
    await clickButton(d,'Save tracking',pane)
    await clickButton(d,'Manage policy',pane)
    await seen(pane.getByPlaceholder('Reason for this policy revision'))
    await d.scroll(pane.getByPlaceholder('Reason for this policy revision'))
  }),
]}
export const archive = {id:'compliance-archive',title:'Arşive kaldırma ve geri alma',route:project,beats:[
  beat('Arşiv onayı','Kullanımdan kalkan bir belgeyi gerekçesiyle arşive alıyoruz. Onay açıkça isteniyor.',async d=>{
    await searchRow(d,'ATL-DOK-017')
    await enterRow(d)
    d.archivedTitle=await drawer(d).locator('.workspace-title').innerText()
    await clickButton(d,'Archive',drawer(d))
    await d.fill(D(d).getByPlaceholder(/Reason for archiving/),'Teslim tamamlandı.')
    await seen(btn(D(d),'Archive document'))
  }),
  beat('Arşiv filtresi','Arşiv filtresini seçtiğimizde kaydı arşivlenmiş belgelerin arasında tekrar buluyoruz.',async d=>{
    await clickButton(d,'Archive document')
    await gone(drawer(d))
    await choose(d,D(d).locator('[aria-label="Compliance document quick filter"]').first(),/^Archived$/)
    await seen(workspaceRows(d).filter({hasText:d.archivedTitle}))
  }),
  beat('Geri yükleme','Gerektiğinde aynı kaydı tekrar etkinleştiriyoruz. Arşiv listesi işlemden sonra güncelleniyor.',async d=>{
    await enterRow(d,d.archivedTitle)
    await btn(drawer(d),'Restore').click({trial:true})
    await clickButton(d,'Restore',drawer(d))
    await clickButton(d,'Restore document')
    await gone(drawer(d))
    await gone(workspaceRows(d).filter({hasText:d.archivedTitle}))
  }),
]}
export const imports = {id:'compliance-import',title:'Excel doğrulaması, aktarım ve denetim',route:project,beats:[
  beat('Excel eşleme ve önizleme','Örnek çalışma kitabının başlıklarını eşliyoruz. Önizleme, kayıtlar değişmeden önce oluşacak sonucu gösteriyor.',async d=>{
    await clickButton(d,'Import Excel')
    await file(d,'compliance.xlsx',modal(d))
    await seen(txt(modal(d),'Automatic linking'))
    await clickText(d,modal(d),'Manual linking')
    await seen(modal(d).locator('.n-select'))
  }),
  beat('Excel doğrulama ve onay','Otomatik eşlemeyi doğruluyoruz. Kaç satırın oluşturulacağı veya güncelleneceği onaydan önce görülebiliyor.',async d=>{
    await clickText(d,modal(d),'Automatic linking')
    await clickButton(d,'Validate import',modal(d))
    await seen(modal(d).getByText(/Create:\s*\d/))
    await d.scroll(btn(modal(d),'Confirm Import'))
  }),
  beat('Aktarım geçmişi ve ayrıntıları','Onaylanan aktarım geçmişe işleniyor. Dosyanın adı, satır sayıları ve işlenen alanlar denetim kaydında yer alıyor.',async d=>{
    await clickButton(d,'Confirm Import',modal(d))
    await gone(modal(d))
    await clickButton(d,'Import history')
    await clickButton(d,'Details',modal(d))
    await seen(txt(modal(d),'Import audit details'))
  }),
]}
export const settings = {id:'compliance-settings',title:'Proje durumları ve kişisel tablo düzeni',route:project,beats:[
  beat('Proje ayarları ve durum ekleme','Yönetici, iş akışında kullanılacak durumu proje için bir kez tanımlıyor.',async d=>{
    await clickButton(d,'Compliance document settings')
    await d.fill(D(d).getByPlaceholder('New status name'),'Yayın sırası')
    await clickButton(d,'Add status')
    await seen(txt(D(d),'Yayın sırası'))
  }),
  beat('Sütunlar ve kişisel görünüm','Tablonun sayfa boyutunu ve sütunlarını birlikte ayarlıyoruz. Bu görünüm kullanılan tarayıcıda saklanıyor.',async d=>{
    const rows=D(d).locator('[aria-label="Rows per page"] input')
    await d.fill(rows,'12')
    await rows.press('Tab')
    await d.click(D(d).getByRole('button',{name:/^Move .+ up$/}).nth(1))
    await clickButton(d,'Save settings')
    await seen(txt(D(d),'All changes saved.'))
  }),
]}
export const outputs = {id:'compliance-export',title:'Tablo özeti ve Excel çıktısı',route:project,beats:[
  beat('Durum, süre ve teslim grafikleri','Tablonun özeti açık sayfadaki belgeler için hesaplanıyor. Durum, bekleme süresi ve teslim eğrisi arasında geçiş yapıyoruz.',async d=>{
    await searchRow(d,'ATL-DOK-001')
    await clickButton(d,'Summary')
    await clickText(d,modal(d),'Pending Days')
    await d.pause(350)
    await clickText(d,modal(d),'Burndown')
    await seen(modal(d).locator('canvas').first())
  }),
  beat('Kayıt listesini Excel olarak indirme','Tüm proje kayıtlarının Excel kopyası hazırlanıyor. İndirme düğmesi hazır olduğunda çalışma kitabını alıyoruz.',async d=>{
    await closeModal(d)
    await clickButton(d,'Export Excel')
    await seen(modal(d).getByText(/current register snapshot is ready/))
    await d.download(()=>clickButton(d,'Download',modal(d)))
  })
]}
export const viewer = {id:'compliance-viewer',title:'Görüntüleyici rolüyle belge inceleme',route:project,role:'viewer',beats:[
  beat('Salt okunur çalışma alanı','Görüntüleyici aynı kayıtları ve işlem geçmişini inceleyebiliyor. Çalışma alanı bu role uygun eylemleri gösteriyor.',async d=>{
    await enterRow(d)
    if (await btn(drawer(d),'Edit').count()) throw Error('Viewer unexpectedly has editing access')
    await drawerTab(d,'Activity')
    await seen(txt(drawer(d),'No recorded activity.').or(drawer(d).locator('.n-timeline')).first())
  })
]}
export const analysis = {id:'document-analysis',title:'Word belgesinde kontrol listesi',route:'/app/compdocs/docAnalyzer',simulated:true,beats:[
  beat('Kişisel analiz sorusu ve belge yükleme','Word belgesini seçip denetim listesine kendi sorumuzu ekliyoruz. Bu soru sonraki belgelerde de kullanılabiliyor.',async d=>{
    await file(d,'atlas.docx')
    await d.fill(D(d).getByPlaceholder('Ask a question to search in the document'),'Belgenin güncel sürümü belirtilmiş mi?')
    await clickButton(d,'Save and select')
    await seen(D(d).locator('.n-list-item').filter({hasText:'Belgenin güncel sürümü'}))
  }),
  beat('Analiz ve özel sonuç dosyası','Seçilen kontrollerle analiz işini başlatıyoruz. Örnek sonuç dosyasını tamamlanan işten indiriyoruz.',async d=>{
    await clickButton(d,'Queue private analysis')
    await resultDownload(d)
  })
]}
export const covers = {id:'document-covers',title:'Excel listesinden kapak oluşturma',route:'/app/compdocs/coverpagecreator',beats:[
  beat('Çalışma kitabı ön kontrolü','Kapak oluşturma ekranı yüklenen dosyada gerekli sütunları arıyor. Yeşil etiketler bulunan başlıkları gösteriyor.',async d=>{
    await file(d,'cover.xlsx')
    await seen(D(d).getByRole('button',{name:'Queue cover-page creation',disabled:false}))
  }),
  beat('Kapak oluşturma ve indirme','Doğrulanan çalışma kitabını kuyruğa alıyoruz. Tamamlanan işin çıktısı aynı ekran üzerinden indirilebiliyor.',async d=>{
    await clickButton(d,'Queue cover-page creation')
    await resultDownload(d)
  })
]}

export const doors = {id:'compliance-doors', title:'DOORS alanlarından belge aktarma',route:project,simulated:true,beats:[
  beat('DOORS modülü ve alanları','Belge modülünün yolunu giriyoruz. Yerel örnekten alınan alanlar, doluluk sayıları ve değer örnekleriyle birlikte geliyor.',async d=>{
    await clickButton(d,'Import DOORS')
    await d.fill(modal(d).getByPlaceholder('/Project/Folder/Module'),'/Atlas/Belgeler')
    await clickButton(d,'Load module fields',modal(d))
    await modal(d).locator('.doors-link-table tbody tr').first().waitFor({timeout:50000})
  }),
  beat('DOORS eşleme ve doğrulama','Modül alanlarının karşılığını kontrol edip doğrulamayı başlatıyoruz. Aynı belge kayıt kuralları burada da uygulanıyor.',async d=>{
    await clickButton(d,'Validate import',modal(d))
    await seen(modal(d).getByText(/Create:\s*\d/))
    await d.scroll(btn(modal(d),'Confirm import'))
  }),
  beat('DOORS aktarım sonucu','Onaydan sonra modülden gelen kaydı belge tablosunda numarasıyla bulabiliyoruz.',async d=>{
    await clickButton(d,'Confirm import',modal(d))
    await gone(modal(d))
    await searchRow(d,'ATL-IMP-D001')
    await enterRow(d)
  }),
]}
export const numbering = {id:'compliance-numbering',title:'Numaratör ile kapak numarası atama',route:project,simulated:true,beats:[
  beat('Yeni belgede numara biçimi','Kapak numarası için proje biçimini seçip seri alanını dolduruyoruz. Atama tamamlandığında belge bu numarayla açılıyor.',async d=>{
    await clickButton(d,'New')
    await clickText(d,modal(d),'Create with Numarator')
    await d.fill(input(modal(d),'Name'),'Atlas teslim numarası örneği')
    await d.fill(modal(d).getByLabel('seri',{exact:false}).and(D(d).locator('input')),'ATL')
    await clickButton(d,'Get number from Numarator',modal(d))
    await gone(modal(d))
    await enterRow(d,'Atlas teslim numarası örneği')
    await seen(drawer(d).getByText(/ATL-KAP-/))
  }),
  beat('Toplu atama seçimi','Açık tablodaki numarasız kayıtları birlikte seçebiliyoruz. Örnekte iki ayrı belgenin kendi kapak numarasına ihtiyacı var.',async d=>{
    await d.click(drawer(d).locator('.n-drawer-header__close'))
    await searchRow(d,'Numara bekleyen')
    await clickButton(d,'Assign missing numbers')
    await seen(modal(d).getByText(/2 of 2 documents selected/))
    await d.fill(modal(d).getByLabel('seri',{exact:false}).and(D(d).locator('input')),'ATL')
  }),
  beat('Toplu atama sonuçları','Atama sonunda her satırda üretilen numara görünüyor. Bu iki numara ayrı belge kayıtlarına yazıldı.',async d=>{
    await clickButton(d,'Assign 2 numbers',modal(d))
    await modal(d).getByText('2 of 2 assigned',{exact:true}).waitFor({timeout:50000})
  }),
]}
export const tableTools={id:'compliance-inspection',title:'Liste filtreleri ve DocProof sürüm kontrolü',route:project,simulated:true,beats:[
  beat('Sütun filtresi','Bir panel seçip filtreyi uyguluyoruz. Tablo yalnızca o panelin belgelerini içeriyor.',async d=>{
    await seen(workspaceRows(d))
    await d.click(D(d).getByLabel('Filter panel',{exact:true}))
    await clickText(d,D(d).locator('.n-popover:visible'),'Belge Yönetimi')
    await clickButton(d,'Confirm',D(d).locator('.n-popover:visible'))
    await seen(workspaceRows(d).filter({hasText:'Belge Yönetimi'}))
  }),
  beat('Tablo sıralaması ve sürüm kontrolü','Sütun başlığıyla sıralamayı değiştiriyoruz. Sürüm denetimi, görünür teknik belge numaraları için tamamlanma sayısını gösteriyor.',async d=>{
    const sortable=D(d).locator('th.n-data-table-th--sortable:visible').first()
    await d.click(sortable)
    await clickButton(d,'Check Issues')
    await seen(D(d).getByText(/Checking the issues is over! Success: [1-9][0-9]*, Fail: 0/))
  }),
]}

export const decisions = {id:'compliance-decisions',title:'Düzeltme isteme, iptal ve bildirim politikası',route:project,simulated:true,beats:[
  beat('Düzeltme talebi','İnceleyici, eksik bir revizyon açıklamasını not ederek belgeyi düzeltmeye gönderebiliyor.',async d=>{
    await searchRow(d,'ATL-DOK-019')
    await enterRow(d)
    await drawerTab(d,'Review & Approval')
    const card=drawer(d).locator('.n-card').filter({has:txt(D(d),'Teslim listesinin sürümünü incele.')})
    await d.fill(card.getByPlaceholder('Decision note'),'Sürüm açıklamasını ekleyin.')
    await clickButton(d,'Request changes',card)
    await seen(txt(card,'changes_requested'))
  }),
  beat('Onay görevi iptali','Ayrıca açılmış bir onay isteği geri alınabiliyor. İptal edilen görevi kararıyla birlikte listede görüyoruz.',async d=>{
    const card=drawer(d).locator('.n-card').filter({has:txt(D(d),'Dizin taslağını onayla.')})
    await d.fill(card.getByPlaceholder('Decision note'),'Düzeltme bekleniyor.')
    await clickButton(d,'Cancel task',card)
    await seen(txt(card,'cancelled'))
  }),
  beat('DocProof kaynağını yenileme','Takip sekmesinde belge sürümünü yeniden sorguluyoruz. Son kontrol zamanı ve örnek kaynak sürümü belgeye kaydediliyor.',async d=>{
    await drawerTab(d,'Tracking & Alerts')
    await clickButton(d,'Refresh',drawer(d))
    await seen(txt(D(d),'DocProof evidence refreshed.'))
  }),
  beat('Proje politikasında yeni sürüm','Yönetici bildirim kuralını değiştirip gerekçesini kaydediyor. Yeni politika sürümü proje için geçerli oluyor.',async d=>{
    const card=drawer(d).locator('.n-card').filter({has:txt(D(d),'Project notification policy')})
    await clickButton(d,'Manage policy',card)
    await d.click(card.locator('.n-switch').first())
    await d.fill(card.getByPlaceholder('Reason for this policy revision'),'Teslim takvimi için bildirim ayarı.')
    await clickButton(d,'Publish revision',card)
    await seen(btn(card,'Manage policy'))
    await d.scroll(btn(card,'Manage policy'))
  })
]}
