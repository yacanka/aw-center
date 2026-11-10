import path from 'node:path'
import {execFileSync} from 'node:child_process'
import {root} from './driver.mjs'
const prepare=task=>async d=>{
  execFileSync(path.join(root,'.venv/bin/python'),[path.join(root,'tools/demo-video/support_fixtures.py'),task],{env:{...process.env,AW_VIDEO_DEMO:'1'}})
  await d.go(new URL(d.page.url()).pathname)
}
const button=(d,name)=>d.page.getByRole('button',{name,exact:true}).first()
const txt=(d,value)=>d.page.getByText(value,{exact:true}).first()
const see=async(d,l)=>{await l.waitFor({state:'visible',timeout:30000});await d.scroll(l);await d.hover(l)}
const click=(d,name)=>d.click(button(d,name))
const upload=async(d,name,i=0)=>d.file(d.page.locator('input[type=file]').nth(i),path.join(d.samples,name))
const step=(feature,text,expected,action,extra={})=>({feature,text,expected,action,...extra})
export const scenes=[
{id:'notice',title:'Sürüm notları ve hatalı adres',role:'editor',route:'/app/home',ready:prepare('release'),beats:[
step('Sürüm notu penceresi','Yeni bir sürüm duyurulduğunda notlar oturumu açan kişiye gösterilir. Güncellemeyi okuyup çalışma alanına geçiyoruz.','Sürüm notu',async d=>{await see(d,d.page.getByRole('dialog').first());await d.hover(d.page.getByRole('dialog').getByRole('button',{name:'close',exact:true}))}),
step('Hatalı adres yönlendirmesi','Geçersiz bir sayfa adresinde geri sayım açılıyor. Uygulama oturum durumuna göre kullanıcıyı başlangıca yönlendiriyor.','404 ekranı ve ana sayfaya dönüş',async d=>{await click(d,'close');await d.go('/app/atlas-gecersiz-sayfa');await txt(d,'404 Not Found').waitFor();await d.page.waitForURL('**/app/home',{timeout:12000})},{during:true})]},
{id:'attention',title:'İlgilenilmesi gereken kayıtlar',route:'/app/home',ready:prepare('attention'),beats:[
step('Uyarıyı erteleme','Bugün ele almayacağımız bir kaydı bir gün erteliyoruz. Kayıt kişisel dikkat listesinden çıkıyor.','Seçilen uyarı kaldırıldı',async d=>{const c=d.page.locator('.action-center .n-list-item').first();const name=await c.locator('.n-thing-header__title').innerText();await d.click(c.getByRole('button',{name:'Snooze 24h'}));await d.page.locator('.action-center .n-list-item').filter({hasText:name}).first().waitFor({state:'hidden'})}),
step('Uyarıyı kapatma onayı','Başka bir uyarıyı kapatırken uygulama onay istiyor. Burada verilen karar kişinin dikkat listesini etkiliyor.','Kapatma onay penceresi',async d=>{await click(d,'Dismiss');await see(d,d.page.getByRole('dialog').first())}),
step('Karardan kaynağa dönüş','Uyarıyı listede tutup kaynak kaydına geçiyoruz. Böylece özetten doğrudan ilgilenilmesi gereken işleme ulaşıyoruz.','İlgili kaydın sayfası',async d=>{await click(d,'Keep');const item=d.page.locator('.action-center .n-list-item').first();await d.click(item.getByRole('button').first());await d.page.waitForURL(u=>u.pathname!='/app/home');await d.pause(400)})]},
{id:'failure',title:'Başarısız işi inceleme',route:'/app/translator',ready:prepare('revision'),simulated:true,beats:[
step('Hata dönen çeviri isteği','Bu kez deneme sözlüğünde bulunmayan bir taslak yüklüyoruz. İşin nasıl sonuçlandığını kendi ekranından izliyoruz.','Taslak için başlatılan iş',async d=>{await upload(d,'taslak.docx');await d.click(d.page.locator('.n-base-selection').first());await d.click(txt(d,'Turkish → English'));await click(d,'Queue translation');await see(d,button(d,'Show in Job Center'))},{during:true}),
step('Hata nedeni ve geçmiş','Çeviri tamamlanamadı. Ayrıntılarda işin durumunu ve kaydedilen açıklamayı görebiliyoruz.','Terminal durum ve olaylar',async d=>{await see(d,txt(d,'failed'));await click(d,'Show in Job Center');await see(d,d.page.locator('.n-drawer').first())})]},
{id:'compare-pdf',title:'PDF metnini karşılaştırma',route:'/app/compare',beats:[
step('PDF metni ve eşleştirme eşiği','PDF sürümlerini yükleyip özel eşleştirme ayarını açıyoruz. Kullanıcı güçlü ve olası metin eşleşmeleri için ayrı eşikler belirleyebiliyor.','Özel karşılaştırma eşikleri',async d=>{await upload(d,'atlas.pdf');await upload(d,'atlas-v2.pdf',1);await d.click(d.page.locator('.n-base-selection').first());await d.click(txt(d,'Custom'));await see(d,d.page.locator('.custom-thresholds').first())}),
step('PDF karşılaştırma raporu','Raporu indirerek metin farklarını inceleyebiliriz. Bu araç PDF içindeki seçilebilir metni kullanıyor.','İndirilen rapor',async d=>{await click(d,'Compare and download');await see(d,button(d,'Download report'));await d.download(()=>click(d,'Download report'))})]},
{id:'ddf-detail',title:'Yorum kaydının ayrıntıları',route:'/app/ddfAssistant',simulated:true,beats:[
step('DDF ayrıntısı ve düzenleme','Belgenin ayrıntı penceresinde revizyonu, inceleyeni ve bölüm bazında yorumları birlikte görebiliyoruz.','Belge bilgi penceresi',async d=>{const row=d.page.getByRole('row').filter({hasText:'ATL-DOK-001'}).first();await d.click(row.getByRole('cell').last().getByRole('button').first());await see(d,d.page.locator('.n-modal').filter({hasText:'Document Information'}))}),
step('Yorumları sınıflandırma','Yorumları sınıflandırmak için analizi çalıştırıyoruz. Sonuç, gösterilmek üzere aynı belge kaydına işleniyor.','Sınıflandırma cevabı',async d=>{await d.page.keyboard.press('Escape');const req=d.page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('ddf')&&r.status()<300);await click(d,'Analyze');await req;await see(d,d.page.locator('.n-modal').filter({hasText:'Result'}).first())})]}
]
// This is the final recording on an explicitly isolated generation. The production
// runner creates a new demo generation before it starts any further recording.
scenes.push({id:'reset-apply',title:'Test ortamında sıfırlamayı onaylama',route:'/app/developer/test-data',ready:prepare('verify-reset'),beats:[
step('Hazırlığı başlatma ve serbest bırakma','Etki tablosunu kontrol ettikten sonra hazırlığı başlatıyoruz. Kaynaklara yeniden yazmak gerekirse hazırlık geri alınabiliyor.','Hazırlık durumu ve geri alma',async d=>{await click(d,'Preview reset');await click(d,'Prepare and cancel related jobs');await see(d,button(d,'Release preparation'));await click(d,'Release preparation');await see(d,button(d,'Prepare and cancel related jobs'))}),
step('Yalnız örnek veriyi sıfırlama','Bu işlem için ayrılmış demo kopyasında onay ifadesini yazıyoruz. Uygulama işlemin tamamlandığını bildiriyor.','Test data was reset.',async d=>{await click(d,'Prepare and cancel related jobs');await see(d,txt(d,'Ready to reset. Review the counts below.'));await d.fill(d.page.locator('main input').last(),'RESET COMPLIANCE AND ORGANIZATION');await click(d,'Reset compliance documents and organization');await see(d,txt(d,'Test data was reset.'))})
]})
