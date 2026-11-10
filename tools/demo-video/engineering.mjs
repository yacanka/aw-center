import path from 'node:path'
import {execFileSync} from 'node:child_process'
import {fileURLToPath} from 'node:url'

function resetProvider(scene) {
  const repo=fileURLToPath(new URL('../../',import.meta.url))
  execFileSync(path.join(repo,'.venv/bin/python'),[path.join(repo,'tools/demo-video/backend_demo/prepare_engineering.py'),scene],{env:{...process.env,AW_VIDEO_DEMO:'1'}})
}

const modulePath = '/Atlas/Belgeler'
const txt = (d, label) => d.page.getByText(label, {exact:true}).first()
const button = (d, label) => d.page.getByRole('button', {name:label, exact:true})
const named = (d, label) => d.page.getByPlaceholder(label, {exact:true})
const beat = (feature, text, expected, action) => ({feature, text, expected, action})

async function show(d, locator) {
  await locator.waitFor({state:'visible', timeout:40000})
  await d.scroll(locator)
  await d.hover(locator)
}
async function option(d, selector, choice) {
  await d.click(selector)
  const option = d.page.locator('.n-base-select-option:visible').filter({has:d.page.getByText(choice,{exact:true})}).first()
  await d.click(option)
}

export const scenes = [
  {
    id:'eslesme', title:'Modülden alan keşfi ve güncelleme eşleştirmesi', route:'/app/doors/scripter', simulated:true,
    beats:[
      beat('Modülden alan adlarını okuma','Güncellenecek kayıtlar için önce modülün alanlarını alıyoruz. Açılan alan listesi, tabloda hangi bilgileri eşleştirebileceğimizi gösteriyor.','Alanları kaldır düğmesi ve başarılı okuma işi',async d=>{
        await d.fill(named(d,'/Project/Module'),modulePath)
        await d.click(button(d,'Load Attributes'))
        await show(d,button(d,'Unload Attributes'))
      }),
      beat('Güncelleme anahtarı ve içerir eşleşmesi','Excel tablosundaki belge numarasını arama anahtarı seçiyoruz. İçerir seçeneği, bu numara alanın içinde geçtiğinde kaydı eşleştiriyor.','Belge anahtarı ve Contains seçimi',async d=>{
        await d.file(d.page.locator('input[type=file]'),path.join(d.samples,'atlas.xlsx'))
        await option(d,d.page.locator('.n-select[aria-label="DOORS attribute for Belge"]'),'Number')
        const key=d.page.getByRole('switch',{name:'Unique Attribute for Belge'})
        if(await key.getAttribute('aria-checked')!=='true') await d.click(key)
        await option(d,d.page.locator('.n-select[aria-label="Match mode for Belge"]'),'Contains')
        await show(d,txt(d,'Contains'))
      }),
      beat('Güncelleme betiğini inceleme','Başlık sütununu hedef alanına bağladık. Üretilen güncelleme betiğini, etkileyeceği satır ve alan sayısıyla birlikte inceleyebiliyoruz.','Altı satırlık güncelleme betiği',async d=>{
        await option(d,d.page.locator('.n-select[aria-label="DOORS attribute for Başlık"]'),'Object Heading')
        await d.click(button(d,'Generate'))
        await show(d,d.page.locator('.n-modal').filter({hasText:'6 rows · 2 mappings'}))
      }),
    ],
  },{
    id:'nesne',title:'DOORS kaydı oluşturma ve güncelleme',route:'/app/developer/doors',simulated:true,ready:()=>resetProvider('nesne'),
    beats:[
      beat('Yeni kayıt oluşturma','Modüle yeni bir dosya teslim maddesi ekliyoruz. İş tamamlandığında oluşan nesnenin numarası, sonuç kartında görünüyor.','Oluşturulan nesnenin numarası',async d=>{
        await d.fill(named(d,'/Project/Folder/Module'),modulePath)
        await d.fill(d.page.locator('.n-input-number input').nth(1),'4')
        await d.fill(d.page.locator('textarea'), JSON.stringify({'Object Heading':'Teslim kontrolü','Object Text':'Revizyonu kayıt altına alın.'},null,2))
        await d.click(button(d,'Queue object create'))
        await show(d,txt(d,'Object created'))
      }),
      beat('Sonuçtaki nesneyi yeniden kullanma','Sonuçtaki numarayı bir sonraki işleme taşıyoruz. Böylece güncelleme doğrudan az önce oluşturduğumuz nesneye uygulanacak.','Seçili mutlak numara',async d=>{
        const result = await d.page.getByText(/^Object: \d+$/).innerText()
        await d.click(button(d,'Use this object for the next operation'))
        const number = d.page.locator('.n-input-number input').first()
        await show(d,number)
        if(await number.inputValue()!==result.match(/\d+/)[0]) throw Error('Oluşturulan nesne forma aktarılmadı.')
      }),
      beat('Nesnenin alanlarını güncelleme','Teslim maddesinin açıklamasını değiştiriyoruz. Sonuç kartı güncellenen nesneyi ve işlemde kullanılan yeni değeri birlikte saklıyor.','Nesne güncelleme sonucu ve değer',async d=>{
        await d.fill(d.page.locator('textarea'), JSON.stringify({'Object Text':'Revizyonu ve yayın tarihini kayıt altına alın.'},null,2))
        await d.click(button(d,'Queue object update'))
        await show(d,txt(d,'Attributes updated'))
      }),
    ],
  },{
    id:'baglama',title:'Eşleşen gereksinim bağlantılarını onaylama',route:'/app/doors/poclinker',simulated:true,ready:()=>resetProvider('baglama'),
    beats:[
      beat('Eşleşmiş grubu inceleme','Kaynak ve hedef modüllerde ortak anahtarları arıyoruz. İlk grubu açınca kaynak gereksinimi ve karşı tarafta bir eşleşme bulunduğunu görüyoruz.','ATL-P-01 grubunda eşleşen ATL-GER-001',async d=>{
        for(const [label,value] of [['/Project/Reference Module',modulePath],['/Project/Target Module','/Atlas/Gereksinimler'],['/Project/Links','/Atlas/BelgeBaglari'],['PoC List','PoC'],['Requirement','Requirement'],['PoC Info','PoC']])await d.fill(named(d,label),value)
        await d.click(button(d,'Queue preview'))
        const group=txt(d,'ATL-P-01')
        await show(d,group)
        await d.click(group)
        await show(d,txt(d,'ATL-GER-001'))
      }),
      beat('Bağlantı onay penceresi','Eşleşmeleri inceledikten sonra bağlantı oluşturma moduna geçiyoruz. Yazma işlemi başlamadan önce uygulama seçilen yön için yönetici onayı istiyor.','Onay ve iptal seçenekleri',async d=>{
        await d.click(d.page.getByRole('switch'))
        await d.click(button(d,'Queue link creation'))
        await show(d,button(d,'Create links'))
      }),
      beat('Bağlantının sonucu ve çıktı','Onaydan sonra sonuç kartı oluşturulan ve daha önce bulunan bağlantıları ayrı gösteriyor. Tam sonuç dosyasını da bu kayıttan indiriyoruz.','Bağlantı oluşturma makbuzu',async d=>{
        await d.click(button(d,'Create links'))
        await show(d,txt(d,'Linker result'))
        const filename = await d.download(()=>d.click(button(d,'Download complete JSON')))
        const { readFile } = await import('node:fs/promises')
        const receipt = JSON.parse(await readFile(filename,'utf8'))
        if(receipt.mode!=='link'||receipt.summary.matched_targets!==4 || receipt.summary.created_links!==4)throw Error('Bağlantı sonucu beklenen eşleşmeleri içermiyor.')
        await show(d,txt(d,'Matched targets'))
      }),
    ],
  },
]

const galleryTitle = 'Atlas yayın özeti'
const galleryRow = d=>d.page.getByRole('row').filter({has:d.page.getByText(galleryTitle,{exact:true})})
const activeSlide = d=>d.page.locator('.n-carousel__slide--current .slide-content').first()
const galleryReceipt = (d, method, part) => d.page.waitForResponse(r=>r.request().method()===method && r.url().includes('/api/tools/presentations/'+part) && r.ok(),{timeout:30000})
async function openGallery(d) {
  // Re-open the gallery after a conversion so the selected carousel reads its final slide set.
  await d.go('/app/pptxGallery')
  const row = galleryRow(d)
  await row.getByText('ready',{exact:true}).waitFor({timeout:45000})
  await d.click(row.getByRole('button',{name:'Show',exact:true}))
  await d.page.locator('img.slide-image').first().waitFor({state:'attached',timeout:20000})
  await show(d, activeSlide(d).locator('img'))
}

scenes.push({
  id:'galeri-bakim',title:'Galeride slayt ve sunum yönetimi',route:'/app/pptxGallery',simulated:true,ready:async d=>{ resetProvider('galeri-bakim'); await d.go('/app/pptxGallery'); await named(d,'Presentation title (optional)').waitFor() },
  beats:[
    beat('Düzenlenecek sunumu seçme','Yayın öncesi kontrol için iki slaytlık bir çalışma kopyası açtık. Galerideki her slayt ayrı ayrı düzenlenebiliyor.','Atlas yayın özeti galeride açık',async d=>{
      await d.fill(named(d,'Presentation title (optional)'),galleryTitle)
      await Promise.all([galleryReceipt(d,'POST','presentations/'),d.file(d.page.locator('input[type=file]').first(),path.join(d.samples,'atlas.pptx'))])
      await galleryRow(d).getByText('ready',{exact:true}).waitFor({timeout:45000})
      await openGallery(d)
    }),
    beat('Slayt görselini değiştirme','Seçili slaytı güncel kapak görseliyle değiştiriyoruz. Galeriyi yeniden açtığımızda yeni görseli aynı sunumda görüyoruz.','Güncellenen slaytın geçerli görseli',async d=>{
      const card=activeSlide(d)
      const position=await card.locator('img').getAttribute('alt')
      await d.hover(card.locator('.n-upload button'))
      await Promise.all([galleryReceipt(d,'PATCH','slides/'),d.file(card.locator('input[type=file]'),path.join(d.samples,'media.png'))])
      await openGallery(d)
      const replaced=d.page.locator('.n-carousel__slide--current img').filter({visible:true}).first()
      if(await replaced.getAttribute('alt')!==position){
        await d.click(d.page.locator('.n-carousel__dot').nth(Number(position.match(/\d+$/)[0])-1))
      }
      await show(d,d.page.locator('.n-carousel__slide--current img').first())
    }),
    beat('Tek slaytı silme','Çalışma kopyasından bir slaytı kaldırıyoruz. Kalan slayt okunabilir halde, sunum galerisinde duruyor.','Silme sonrası tek slayt',async d=>{
      const card=activeSlide(d)
      const oldAlt=await card.locator('img').getAttribute('alt')
      await Promise.all([galleryReceipt(d,'DELETE','slides/'),d.click(card.locator('button.n-button--error-type'))])
      await d.page.reload({waitUntil:'domcontentloaded'})
      const row=galleryRow(d)
      await row.getByRole('cell',{name:'1',exact:true}).waitFor({timeout:40000})
      await d.click(row.getByRole('button',{name:'Show',exact:true}))
      const remaining=d.page.locator('img.slide-image').first()
      await show(d,remaining)
      if(await remaining.getAttribute('alt')===oldAlt) throw Error('Silinen slayt hâlâ görünür.')
    }),
    beat('Kaynak sunumdan yeniden dönüştürme','Yeniden dönüştürme işlemi kaynak sunumu okuyor. İş tamamlanınca iki slayt tekrar listede görünüyor.','Başarılı iş ve iki slayt',async d=>{
      const row=galleryRow(d)
      await Promise.all([galleryReceipt(d,'POST','presentations/'),d.click(row.getByRole('button',{name:'Re-Convert',exact:true}))])
      await row.getByRole('cell',{name:'2',exact:true}).waitFor({timeout:45000})
      await show(d,row.getByText('ready',{exact:true}))
    }),
    beat('Çalışma kopyasını silme','İnceleme bittiğinde yalnızca bu çalışma kopyasını siliyoruz. Galeri listesinde diğer sunumlar kullanılmaya devam ediyor.','Çalışma kopyası listeden kaldırıldı',async d=>{
      const row=galleryRow(d)
      await Promise.all([galleryReceipt(d,'DELETE','presentations/'),d.click(row.getByRole('button',{name:'Delete',exact:true}))])
      await row.waitFor({state:'detached'})
      await show(d,d.page.getByRole('columnheader',{name:'Title'}))
    }),
  ]
})
