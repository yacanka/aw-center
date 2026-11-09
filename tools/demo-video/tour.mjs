import path from 'node:path'
const t=(d,name)=>d.page.getByText(name,{exact:true}).first()
const btn=(d,name)=>d.page.getByRole('button',{name,exact:true}).first()
const ph=(d,name)=>d.page.getByPlaceholder(name,{exact:true}).first()
const wait=loc=>loc.waitFor({state:'visible',timeout:18000})
const see=async(d,name)=>{const l=t(d,name);await wait(l);await d.scroll(l);await d.hover(l)}
const click=async(d,name)=>d.click(btn(d,name))
const choose=async(d,index,value)=>{await d.click(d.page.locator('.n-base-selection').nth(index));await d.click(t(d,value))}
const file=async(d,name,i=0)=>d.file(d.page.locator('input[type=file]').nth(i),path.join(d.samples,name))
const b=(feature,text,action,expected,extra={})=>({feature,text,action,expected,...extra})
export const scenes=[
{id:'intro',title:'AW Center ile bir çalışma günü',route:'/app/home',beats:[
b('Örnek veri ve kapsam','AW Center tanıtımına hoş geldiniz. Bu oturumda Atlas projesine ait kurgusal kayıtları kullanıyoruz.',async d=>{await wait(d.page.getByRole('heading',{name:'AW Center',exact:true}));await d.hover(d.page.getByRole('heading',{name:'AW Center',exact:true}))},'Ana çalışma alanı'),
b('Aksiyon merkezi','Dış sistem yanıtları ve bazı iş sonuçları bu ortamda temsilîdir. Ana sayfada ilgilenmemiz gereken kayıtları görüyoruz.',async d=>{const l=t(d,'Needs attention');await wait(l);await d.hover(l)},'Action Center'),
b('İş özeti','Bir yönetici, ekibin gündemini gözden geçirirken kendi hesabındaki bekleyen ve sonuçlanan işlemleri de buradan izleyebilir.',async d=>{await see(d,'My work')},'Kullanıcının iş özeti')]},
{id:'login',title:'Oturum açma ve gezinme',role:'public',route:'/app/login',beats:[
b('Hesap kurtarma','Giriş ekranındaki parola kurtarma formu, kayıtlı e-posta adresiyle başvuru yapmayı sağlar.',async d=>{await click(d,'Forgot Password?');await wait(ph(d,'Enter your email'));await d.hover(ph(d,'Enter your email'))},'Kurtarma formu görünür'),
b('Oturum açma','Örnek yönetici hesabıyla oturum açıyoruz. Menü, hesabın erişebildiği uygulamaları gösteriyor.',async d=>{await d.go('/app/login');await d.fill(d.page.getByRole('textbox',{name:'Username'}),d.credentials().username);await d.fill(d.page.getByLabel('Password',{exact:true}),d.credentials().password);await click(d,'Login');await wait(d.page.getByRole('button',{name:'Quick command'}))},'Ana çalışma alanı ve yetkili menü'),
b('Komut arama','Hızlı aramaya aracın adını yazınca ilgili çalışma alanına doğrudan geçebiliyoruz.',async d=>{await click(d,'Quick command');await d.fill(d.page.getByPlaceholder('Search a tool, process, or integration…'),'Compare');await d.click(d.page.locator('.command-modal button').filter({hasText:'Compare'}).first());await wait(t(d,'Old file'))},'Karşılaştırma ekranı açılır')]},
{id:'pilot',title:'Word belgesini çevirme',route:'/app/translator',simulated:true,beats:[
b('Çeviri girdisi ve yönü','Atlas belgesini seçip çeviri yönünü Türkçeden İngilizceye ayarlıyoruz.',async d=>{await file(d,'atlas.docx');await choose(d,0,'Turkish → English')},'Belge adı ve çeviri yönü', {during:true}),
b('Çeviri işi ve ilerleme','Çeviriyi başlatıyoruz. İlerleme çubuğu, belgenin hangi aşamada olduğunu gösteriyor.',async d=>{await click(d,'Queue translation');await wait(btn(d,'Show in Job Center'));await d.scroll(btn(d,'Show in Job Center'))},'İş kartı ve ilerleme',{during:true}),
b('Çeviri sonucunu indirme','İş tamamlandı. İngilizce örnek belgeyi sonuç düğmesinden indiriyoruz.',async d=>{await wait(btn(d,'Download result'));await d.download(()=>click(d,'Download result'))},'Başarılı iş ve indirilebilir DOCX')]},
{id:'jobs',title:'İş geçmişi ve sonuçlar',route:'/app/jobs',beats:[
b('İş listesi','İş Merkezi, bu hesaba ait işlemleri bir arada tutuyor. Liste, sayfadan ayrıldıktan sonra da erişilebilir.',async d=>{await wait(btn(d,'Refresh'));await click(d,'Refresh');await wait(btn(d,'Details'))},'İş listesi yenilendi'),
b('İş ayrıntıları ve olay geçmişi','Bir işlemin ayrıntılarını açınca deneme sayısını, durumunu ve kaydedilmiş olayları aynı yerde inceleyebiliyoruz.',async d=>{await click(d,'Details');await wait(d.page.locator('.n-drawer'));await d.hover(d.page.locator('.n-drawer').first())},'İş ayrıntı çekmecesi')]},
{id:'compare',title:'İki belge sürümünü karşılaştırma',route:'/app/compare',beats:[
b('Sürüm ve belge ailesi','Aynı planın eski ve yeni sürümünü yüklüyoruz. Uygulama dosya türünü tanıyor ve metin karşılaştırmasını seçiyor.',async d=>{await file(d,'atlas.docx');await file(d,'atlas-v2.docx',1);await wait(t(d,'Word text'))},'Word metni olarak tanındı'),
b('Karşılaştırma ve rapor','Karşılaştırmayı başlatıyoruz. Tamamlanan işin değişiklik raporu bu ekrandan indirilebiliyor.',async d=>{await click(d,'Compare and download');await wait(btn(d,'Download report'));await d.download(()=>click(d,'Download report'))},'İndirilen karşılaştırma raporu')]},
{id:'pdf',title:'PDF belgesini parçalara ayırma',route:'/app/pdf/split',beats:[
b('PDF ve grup sayısı','Toplantı dosyasını iki gruba ayırmak için PDF belgesini yükleyip parça sayısını giriyoruz.',async d=>{await file(d,'atlas.pdf');await d.fill(ph(d,'Parts'),'2');await wait(btn(d,'Split'))},'İki parçalı bölme isteği'),
b('Bölünmüş PDF arşivi','Bölme işlemi tamamlandığında sayfalar ayrı PDF dosyaları olarak tek arşivde indiriliyor.',async d=>{await d.download(()=>click(d,'Split'));await wait(t(d,'Split completed'))},'Açılabilir ZIP arşivi')]},
{id:'media',title:'Medya önizleme ve dönüştürme',route:'/app/media-converter',beats:[
b('Medya ve hedef biçim','Proje görselini yüklüyor, çıktı biçimini seçiyoruz. Genişlik ve yükseklik de bu formda belirlenebiliyor.',async d=>{await file(d,'media.png');await choose(d,0,'JPG');await d.fill(d.page.locator('.n-input-number input').first(),'640')},'Kaynak görsel ve JPEG ayarı'),
b('Boyut tahmini','Önizleme, dönüştürme başlamadan önce tahmin edilen dosya boyutunu gösteriyor.',async d=>{await click(d,'Preview output size');await see(d,'Output preview')},'Boyut tahmini'),
b('Medya çıktısı','İş tamamlanınca dönüştürülen görseli indiriyoruz. İş kaydı geçmişte de bulunabiliyor.',async d=>{await click(d,'Queue conversion');await wait(btn(d,'Download result'));await d.download(()=>click(d,'Download result'))},'JPEG çıktı')]},
{id:'hub',title:'Entegrasyonların bağlantı durumu',route:'/app/integrations',simulated:true,beats:[
b('Katalog ve canlı kontroller','Entegrasyon merkezinde tanımlı bağlantıları görüyoruz. Kontrolü çalıştırınca her kart kendi bağlantı sonucunu gösteriyor.',async d=>{await click(d,'Run live checks');await wait(d.page.locator('.health-meta').first());await d.hover(d.page.locator('.health-meta').first())},'Bağlantı sonuçları ve kontrol zamanı')]},
{id:'viewer',title:'Görüntüleyici rolü',role:'viewer',route:'/app/home',beats:[
b('Görüntüleyici menüsü','Bu kez görüntüleyici hesabındayız. Menü ve hızlı arama bu kişinin erişimine göre hazırlanıyor.',async d=>{const close=d.page.getByRole('dialog').getByRole('button',{name:'close',exact:true});if(await close.isVisible())await d.click(close);await click(d,'Quick command');await d.fill(d.page.getByPlaceholder('Search a tool, process, or integration…'),'Atlas')},'Görüntüleyici araması'),
b('Yetki sınırı','Aynı kişi yönetim sayfasına gitmek istediğinde uygulama erişim sınırını açıklıyor.',async d=>{await d.go('/app/users');await wait(t(d,'Access denied'))},'Erişim reddi')]},
{id:'closing',title:'Çalışmanın sonucuna dönmek',route:'/app/jobs',beats:[
b('Kapanış','Atlas örneğinde bir belgeyi işledik, değişiklikleri karşılaştırdık ve sonuçları indirdik. İş geçmişi, bu çıktılara yeniden ulaşabileceğimiz yer.',async d=>{await click(d,'Refresh');await wait(btn(d,'Details'));await d.hover(btn(d,'Details'))},'İş geçmişi')]}
]
