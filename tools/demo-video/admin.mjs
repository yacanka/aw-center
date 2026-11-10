import path from 'node:path'
import {spawnSync} from 'node:child_process'
import {fileURLToPath} from 'node:url'
import {createHmac,randomBytes} from 'node:crypto'

const step = (feature, text, expected, action, during=false) => ({feature, text, expected, action, during})
const shown = loc => loc.waitFor({state:'visible',timeout:30000})
const hidden = loc => loc.waitFor({state:'hidden',timeout:30000})
const txt = (d, name) => d.page.getByText(name,{exact:true}).first()
const btn = (d, name, parent=d.page) => parent.getByRole('button',{name,exact:true}).first()
const click = (d, name, parent=d.page) => d.click(btn(d,name,parent))
const hint = (d, value) => d.page.getByPlaceholder(value,{exact:true}).first()
const row = (d, value) => d.page.locator('tr:visible').filter({hasText:value}).first()
const modal = d => d.page.locator('.n-modal:visible').last()
const dialog = d => d.page.locator('.n-dialog:visible').last()
const select = async (d, loc, option) => {
  await d.click(loc)
  await d.click(d.page.locator('.n-base-select-option').filter({hasText:option}).first())
}
const see = async (d,loc) => { await shown(loc); await d.scroll(loc); await d.hover(loc) }
const tab = async (d, name) => d.click(d.page.getByText(name,{exact:true}).filter({visible:true}).first())
const upload = (d, file) => d.file(modal(d).locator('input[type=file]'),path.join(d.samples,file))
const box = (d,i) => modal(d).locator('input:not([type=checkbox])').nth(i)
const icon = (d,key,i) => d.click(row(d,key).getByRole('button').nth(i))
const roleCard = d => d.page.locator('.role-grid article').filter({hasText:'Atlas Okuma Grubu'})
const createInvite = async (d, email) => {
  await click(d,'Create invitation link')
  await d.fill(modal(d).locator('input').first(),email)
  await click(d,'Create link',modal(d)); await shown(btn(d,'Done',modal(d)))
  return new URL(await modal(d).locator('textarea').inputValue())
}
const registerEmail='atlas.davet@example.invalid'
async function resetInvitedDemo(d){
  const existing=row(d,registerEmail)
  await shown(btn(d,'Create invitation link'));await shown(row(d,'D10001'))
  if(await existing.isVisible()){
    await click(d,'Delete',existing);await click(d,'Delete account',dialog(d));await hidden(existing)
  }
}
let invitation

export const scenes=[
  {id:'accounts',title:'Kullanıcı dizini ve ortak roller',route:'/app/users',beats:[
    step('Dizin filtresi ve erişim ayrıntısı','Kullanıcıyı siciliyle arıyoruz. Satırı genişletince hangi projede, hangi uygulamaya erişebildiğini görüyoruz.','Filtrelenen hesap ve genişletilmiş erişim',async d=>{
      await d.fill(hint(d,'Search name, username or email'),'D10003');await hint(d,'Search name, username or email').press('Enter')
      const r=row(d,'D10003');await shown(r);await d.click(r.locator('.n-data-table-expand-trigger'));await see(d,d.page.locator('.access-details').first())
    }),
    step('Kullanıcı yetki düzenleyicisi','Yönetim penceresinde grup üyeliği, doğrudan izinler ve proje erişiminin kaynağı birlikte incelenebilir.','Proje atamaları ve izin araması', async d=>{
      await click(d,'Manage',row(d,'D10003'));await shown(modal(d));await d.fill(hint(d,'Search permissions or modules'),'view user');await see(d,hint(d,'Search permissions or modules'))
    }),
    step('Hesap silme onayı','Silme işlemi ayrıca onay istiyor. Bu hesabı korumak için uyarıyı kapatıyoruz.','Hesap silme onay penceresi',async d=>{
      await click(d,'Cancel',modal(d));await click(d,'Delete',row(d,'D10003'));await see(d,btn(d,'Delete account'))
    }),
    step('Ortak rol oluşturma','Örnek okuma grubu için bir rol oluşturup kullanıcı listesini görüntüleme iznini seçiyoruz.','Oluşturulan ortak rol', async d=>{
      await click(d,'Cancel',dialog(d));await click(d,'Create role');await d.fill(hint(d,'Enter a role name'),'Atlas Okuma Grubu');await d.fill(hint(d,'Search permissions or modules'),'Can view user');await d.click(modal(d).getByRole('checkbox',{name:'Can view user',exact:true}));await click(d,'Create role',modal(d));await see(d,roleCard(d))
    },true),
    step('Ortak rol güncelleme','Bir rolün izinleri değiştiğinde o rolün üyeleri de etkilenir. Düzenleme penceresi bu etkiyi kayıttan önce gösterir.','Rol değişikliğinin etkisi',async d=>{
      await click(d,'Edit role',roleCard(d));await see(d,txt(d,'Saving changes updates access for every member of this role.'));await click(d,'Save role for all members',modal(d));await shown(roleCard(d))
    }),
    step('Ortak rolü kaldırma','Deneme grubunu kaldırıyoruz. Onaydan sonra grup ortak rol listesinden çıkıyor.','Onaylanan rol silme',async d=>{
      await click(d,'Delete',roleCard(d));await click(d,'Delete role',dialog(d));await hidden(roleCard(d));await see(d,btn(d,'Create role'))
    })]},
  {id:'invites',title:'Davetten hesap açılışına',route:'/app/users',ready:resetInvitedDemo,beats:[
    step('Davetiye üretme','Yeni ekip üyesine, yalnızca kurgusal e-posta adresiyle kullanılabilen bir davet oluşturuyoruz.','Davetiye oluşturuldu',async d=>{invitation=await createInvite(d,registerEmail);await d.hover(btn(d,'Done',modal(d)))},true),
    step('Davetli kayıt formu','Daveti alan kişi kendi hesabını açıyor. E-posta adresi davetten geliyor, kullanıcı adı ve parola bu ekranda belirleniyor.','Davetli hesap bilgileri girildi',async d=>{
      await click(d,'Done',modal(d));await d.go('/app/settings');await click(d,'Sign out');await shown(btn(d,'Login'));await d.go(invitation.pathname+invitation.search+invitation.hash)
      await shown(hint(d,'U12345'));await d.fill(hint(d,'U12345'),'D91002');await d.fill(d.page.locator('.invite-card input').nth(2),'Güneş');await d.fill(d.page.locator('.invite-card input').nth(3),'Örnek')
      const generated=randomBytes(18).toString('base64url');for(const input of await d.page.locator('input[type=password]').all())await d.fill(input,generated)
    }),
    step('Davet kabulü','Kayıt tamamlanınca uygulama giriş ekranına dönüyor. Yönetici davetin kullanıldığını işlem geçmişinde görebilir.','Başarılı hesap kaydı ve giriş ekranı',async d=>{await click(d,'Create account');await shown(btn(d,'Login'))})]},
  {id:'invitation-audit',title:'Davet geçmişi ve hesap yönetimi',route:'/app/users',ready:prepareInvitationAudit,beats:[
    step('Davetiye geçmişi','E-posta adresiyle aradığımızda davetin kullanıldığı hesabı ve işlem tarihlerini görüyoruz.','Kullanılan davet ve hesabı',async d=>{await click(d,'Manage invitations');await d.fill(hint(d,'Search email or username'),registerEmail);await click(d,'Search',modal(d));await see(d,row(d,'D91002'))}),
    step('Açık daveti geri çekme','Ayrı bir daveti geri çekiyoruz. Durum değiştiğinde bu bağlantıyla kayıt açılamaz.','İptal edilen ikinci davet',async d=>{
      await d.page.keyboard.press('Escape');await createInvite(d,'atlas.iptal@example.invalid');await click(d,'Done',modal(d));await click(d,'Manage invitations');await d.fill(hint(d,'Search email or username'),'atlas.iptal@example.invalid');await click(d,'Search',modal(d));const active=row(d,'atlas.iptal@example.invalid');await click(d,'Revoke',active);await click(d,'Revoke',dialog(d));await see(d,active.getByText('Revoked',{exact:true}))
    }),
    step('Geçici hesabı kaldırma','Tanıtım için açılan hesabı dizinde buluyor ve silmeyi onaylıyoruz. Arama sonucu boşalıyor.','Geçici hesap dizinden kaldırıldı',async d=>{
      await d.page.keyboard.press('Escape');await d.fill(hint(d,'Search name, username or email'),'D91002');await hint(d,'Search name, username or email').press('Enter');await click(d,'Delete',row(d,registerEmail));await click(d,'Delete account',dialog(d));await hidden(row(d,registerEmail));await see(d,txt(d,'0 results'))
    })]},
  {id:'settings',title:'Profil, görünüm ve hesap güvenliği',route:'/app/settings',role:'editor',ready:async d=>{const release=d.page.getByRole('dialog').filter({hasText:'Release Notes'});if(await release.isVisible())await click(d,'close',release)},beats:[
    step('Profil güncelleme','Kullanıcı kendi profilini düzenleyebilir. Ad değişikliği kaydedilince hesap kartına hemen yansır.','Hesap kartında güncellenmiş ad',async d=>{
      const first=d.page.locator('#profile-first-name');const old=await first.inputValue();const update=old==='Ekin Atlas'?'Ekin':'Ekin Atlas';await d.fill(first,update);await click(d,'Save profile');await see(d,d.page.locator('#account-heading').filter({hasText:update}))
    },true),
    step('Tema ve görünüm','Koyu temayı seçtiğimizde sayfanın tamamı aynı görünüme geçiyor. Tercih bu kullanıcı için saklanıyor.','Koyu tema seçildi',async d=>{await d.click(d.page.locator('label.theme-option').filter({hasText:'Dark'}));await shown(d.page.locator('label.theme-option.selected').filter({hasText:'Dark'}))}),
    step('Dil tercihi','Hesap ayarları dil seçeneklerini de gösteriyor. Bu sürümde İngilizce kullanılabiliyor, Türkçe seçenek hazırlık aşamasında.','Arayüz dili seçenekleri',async d=>{await d.click(d.page.locator('label.theme-option').filter({hasText:'Light'}));await d.click(d.page.locator('.language-select .n-base-selection'));await see(d,d.page.locator('.n-base-select-menu').first())}),
    step('Parola ve oturum','Parola değiştirmek için mevcut parola ve iki eşleşen yeni değer gerekiyor. Hesap güvenliği bölümünden bu oturum kapatılabiliyor.','Parola değiştirme formu',async d=>{await d.page.keyboard.press('Escape');await click(d,'Change password');await see(d,hint(d,'Enter new password again'))})]},
]

const chooseAtlas = async d => {
  const item = d.page.getByText('Atlas Demo Projesi',{exact:true}).filter({visible:true}).first()
  await shown(item);await d.click(item)
}
const removePerson=async (d,key)=>{await icon(d,key,1);await click(d,'Yes',dialog(d));await hidden(row(d,key))}
const panelName='Atlas Geçici Paneli'
scenes.push(
  {id:'people',title:'Organizasyon ve kişi dizini',route:'/app/organization',ready:async d=>{await shown(row(d,'D10001'));for(const id of ['D91003','D91001'])if(await row(d,id).isVisible())await removePerson(d,id)},beats:[
    step('Kişi ekleme','Ekipte görev alacak kişiyi sicili, adı ve kurgusal e-posta adresiyle dizine ekliyoruz.','Yeni kişi listede',async d=>{
      await click(d,'New Person');await d.fill(box(d,0),'D91003');await d.fill(box(d,1),'Irmak Örnek');await d.fill(box(d,2),'irmak@example.invalid');await click(d,'Add',modal(d));await see(d,row(d,'D91003'))
    },true),
    step('Dizin düzenleme ve arama','Kaydın adını düzenliyoruz. Güncel değer hem dizindeki satırda hem de aramada aynı kişiyi gösteriyor.','Düzenlenen kayıt arama listesinde',async d=>{
      await icon(d,'D91003',0);await d.fill(box(d,1),'Irmak Atlas');await click(d,'Update',modal(d));await see(d,row(d,'Irmak Atlas'));await d.fill(hint(d,'Search'),'Irmak');await hint(d,'Search').press('Enter');await shown(row(d,'Irmak Atlas'))
    }),
    step('Kişi silme ve dosyadan ekleme','Deneme kaydını kaldırıp kişi listesini Excel üzerinden alıyoruz. Dosyadaki yeni kişi dizinde kendi siciliyle yer alıyor.','Excel dosyasından eklenen kişi',async d=>{
      await removePerson(d,'D91003');await d.go('/app/organization');await click(d,'Import People');await upload(d,'people.xlsx');await modal(d).waitFor({state:'hidden',timeout:30000});await see(d,row(d,'D91001'))
    }),
    step('Dizin temizleme onayı','Bir dizin kaydını kaldırmadan önce son bir onay istenir. Örnek içe aktarma kaydını burada kapatıyoruz.','Geçici kaydın kaldırılması',async d=>{await removePerson(d,'D91001');await see(d,txt(d,'People List'))})]},
  {id:'panels',title:'Proje panelleri ve toplu aktarım',route:'/app/organization',beats:[
    step('Panel tanımlama','Atlas projesinde bir panel oluşturuyoruz. Bölüm kodu, ad ve disiplin aynı kayıtta yer alıyor.','Yeni proje paneli',async d=>{
      await tab(d,'Panels');await chooseAtlas(d);await click(d,'New Panel');const ins=modal(d).locator('.n-input input');await d.fill(ins.nth(0),panelName);await d.fill(ins.nth(1),'Kalite');await d.fill(ins.nth(2),'97-00');await click(d,'Add',modal(d));await see(d,row(d,'97-00'))
    },true),
    step('Panel düzenleme','Panelin disiplin bilgisini gözden geçirip güncelliyoruz. Liste aynı bölüm koduyla yeni disiplini gösteriyor.','Düzenlenen disiplin',async d=>{await icon(d,'97-00',0);await d.fill(modal(d).locator('.n-input input').nth(1),'Belge Kontrolü');await click(d,'Update',modal(d));await see(d,row(d,'97-00').getByText('Belge Kontrolü',{exact:true}))}),
    step('Panel içe aktarma önizlemesi','Toplu güncellemede dosyanın sütunları önizlemeye geliyor. Yönetici, yeni ve değişen kayıt sayılarını onaydan önce görebilir.','Aktarım eşleştirmesi ve sayı özeti',async d=>{await click(d,'Import Excel');await upload(d,'panels.xlsx');await see(d,txt(d,'Confirm Panel Import'))}),
    step('Aktarımı onaylama','Aktarımı onayladığımızda yeni panel proje tablosuna ekleniyor. Bölüm kodu bu satırı tanımlıyor.','Dosya İzleme paneli',async d=>{await click(d,'Confirm Import',modal(d));await see(d,row(d,'98-00'))}),
    step('Panel silme ve proje kataloğu','Kullanılmayan deneme panellerini onayla kaldırıyoruz. Projeler sekmesinde tanımlı projelerin durumunu okuyabiliriz.','Proje kataloğu',async d=>{
      for(const key of ['97-00','98-00']){await icon(d,key,1);await click(d,'Delete',dialog(d));await hidden(row(d,key))}
      await tab(d,'Projects');await see(d,row(d,'Atlas Demo Projesi'))
    })]},
  {id:'assignments',title:'Panel sorumluları',route:'/app/organization',beats:[
    step('Sorumlu ekleme formu','Yeni sorumluluk tanımında paneli, görev türünü ve dizindeki kişiyi seçiyoruz.','Panel, rol ve kişi alanları',async d=>{
      await tab(d,'Responsibles');await chooseAtlas(d);await click(d,'New Responsible');const selectors=modal(d).locator('.n-base-selection');await select(d,selectors.nth(1),'21-00');await select(d,selectors.nth(2),'SSB');await d.fill(hint(d,'Search People by ID, name, or email'),'Bora');await d.click(d.page.locator('.n-dropdown-option').filter({hasText:'D10006'}).first());await see(d,btn(d,'Add',modal(d)))
    },true),
    step('Panel doğrulama sonucu','Bu sürümde panel seçimi doğrulamaya takılıyor. Ekrandaki uyarı nedeniyle bu yeni atama kaydedilmiyor.','Ürünün gerçek doğrulama uyarısı',async d=>{await click(d,'Add',modal(d));await see(d,txt(d,'panel is not a string'))}),
    step('Panel filtresi','Panel filtresini açıp bölüm seçebiliyoruz. Bu sürümde liste, kayıtlı örnek atamalar olmasına rağmen boş görünüyor.','Filtre ve gerçek boş tablo',async d=>{await d.page.keyboard.press('Escape');await select(d,d.page.locator('.n-base-selection').first(),'21-00');await see(d,txt(d,'No Data'))})]}
)

// The sixth fixture account has no recording dependencies. Even an interrupted take can
// derive its alternate password from this generation's random seed credential.
const securityUser='D10006'
const alternatePassword=d=>createHmac('sha256',d.credentials().password).update('aw-center-video/member-password').digest('hex')+'aA'
async function localPost(d, endpoint, data){
  const origin=new URL(d.page.url()).origin
  if(origin!=='http://127.0.0.1:18765')throw Error('Account reset requires the isolated demo origin')
  const context=d.page.context()
  const cookie=(await context.cookies()).find(c=>c.name==='csrftoken')
  if(!cookie)throw Error('Demo CSRF token missing')
  return context.request.post(origin+endpoint,{data,headers:{Origin:origin,'X-CSRFToken':cookie.value}})
}
async function restoreMember(d){
  const changed=await localPost(d,'/api/users/password/',{current_password:alternatePassword(d),new_password:d.credentials().password,confirm_password:d.credentials().password})
  if(!changed.ok())throw Error('Demo member credential reset failed with '+changed.status())
}
async function prepareMember(d){
  const context=d.page.context(); const origin=new URL(d.page.url()).origin
  await context.request.get(origin+'/api/session/')
  const signIn=password=>localPost(d,'/api/session/',{username:securityUser,password})
  const first=await signIn(d.credentials().password)
  if(!first.ok()){
    const alternate=await signIn(alternatePassword(d));if(!alternate.ok())throw Error('Demo member session unavailable')
    await restoreMember(d)
  }
  await d.go('/app/settings');await shown(btn(d,'Change password'));await d.pause(450)
  const release=d.page.getByRole('dialog').filter({hasText:'Release Notes'});if(await release.isVisible())await click(d,'close',release)
}
scenes.push({id:'member-password',title:'Parola değişikliği ve yeni oturum',role:'public',displayRole:'Kişisel hesap',route:'/app/login',ready:prepareMember,beats:[
  step('Kişisel parolayı değiştir','Örnek kullanıcı mevcut parolasını giriyor. Yeni parolayı ikinci kez yazarak değişikliği onaylıyor.','Parola güncellendi ve form kapandı',async d=>{
    await click(d,'Change password');await d.fill(hint(d,'Enter password'),d.credentials().password);await d.fill(hint(d,'Enter new password'),alternatePassword(d));await d.fill(hint(d,'Enter new password again'),alternatePassword(d));await click(d,'Save',modal(d));await hidden(modal(d))
  },true),
  step('Yeni parolayla oturum','Oturumu kapatıp yeni parolayla yeniden giriş yapıyoruz. Kişisel çalışma alanı yeniden açılıyor.','Güncellenen parola ile başarılı oturum',async d=>{
    await click(d,'Sign out');await shown(btn(d,'Login'));await d.fill(d.page.getByRole('textbox',{name:'Username'}),securityUser);await d.fill(d.page.getByLabel('Password',{exact:true}),alternatePassword(d));await click(d,'Login');await shown(btn(d,'Quick command'));await restoreMember(d)
  },true)
]})

// A partial rerun may reuse the registration footage against a freshly reset demo DB.
// Re-create that same audit prerequisite through the original forms outside capture.
async function prepareInvitationAudit(d){
  await shown(row(d,'D10001'))
  if(await row(d,registerEmail).isVisible())return
  const registration=scenes.find(scene=>scene.id==='invites')
  for(const beat of registration.beats)await beat.action(d)
  const result=await localPost(d,'/api/session/',d.credentials())
  if(!result.ok())throw Error('Could not resume the isolated admin session')
  await d.go('/app/users');await shown(row(d,registerEmail))
}

const recoveryUser='D10005'
const recoveredPassword=d=>createHmac('sha256',d.credentials().password).update('aw-center-video/recovered-member').digest('hex')+'rA'
async function openRecoveryMessage(d){
  const root=fileURLToPath(new URL('../../',import.meta.url));const python=path.join(root,'.venv/bin/python')
  const delivery=spawnSync(python,[path.join(root,'tools/demo-video/audio/recovery_mail.py')],{
    cwd:root,env:{...process.env,AW_VIDEO_DEMO:'1'},stdio:['ignore','ignore','ignore','pipe'],timeout:60000
  })
  if(delivery.status!==0 || !delivery.output[3]?.length)throw Error('Private demo mail delivery failed')
  // The real UI scrubs this fragment during bootstrap. Keep the URL out of action/error logs.
  let target=delivery.output[3].toString('utf8');delivery.output[3].fill(0)
  try{
    await d.page.goto(target,{waitUntil:'domcontentloaded'});target=''
    if(new URL(d.page.url()).hash)await d.page.reload({waitUntil:'domcontentloaded'})
    await shown(hint(d,'Enter your new password'))
    if(new URL(d.page.url()).hash)throw Error()
  }catch{throw Error('The local reset link did not open a clean password form.')}
}
scenes.push({id:'public-recovery',title:'E-postayla parola kurtarma',role:'public',route:'/app/login',beats:[
  step('Hesap varlığını açıklamayan başvuru','Parolasını unutan kullanıcı giriş sayfasından e-posta adresini gönderiyor. Ekrandaki yanıt, bu adresle bir hesap olup olmadığını açıklamıyor.','Kurtarma başvurusunun tarafsız onayı',async d=>{
    await click(d,'Forgot Password?');await d.fill(hint(d,'Enter your email'),'d10005@example.invalid');await click(d,'Send',modal(d));await see(d,txt(d,'A password reset link has been sent to your email.'))
  },true),
  step('Kurtarma bağlantısından yeni parola formu','Yerel posta kutusuna gelen bağlantıyı açıyoruz. Yeni parola iki alana giriliyor. Form açıldığında bağlantının gizli bölümü adres çubuğundan temizlenmiş oluyor.','Yerel posta bağlantısı doğrulandı, yeni parola alanları dolduruldu',async d=>{
    await openRecoveryMessage(d);await d.fill(hint(d,'Enter your new password'),recoveredPassword(d));await d.fill(hint(d,'Enter your new password again'),recoveredPassword(d))
  }),
  step('Kurtarma işlemi ve oturum doğrulaması','Parolayı güncelliyor ve aynı sicille yeniden giriş yapıyoruz. Çalışma alanının açılması, kurtarılan hesabın kullanılabildiğini gösteriyor.','Yeni parola ile başarılı giriş',async d=>{
    await click(d,'Update');await shown(btn(d,'Login'));await d.fill(d.page.getByRole('textbox',{name:'Username'}),recoveryUser);await d.fill(d.page.getByLabel('Password',{exact:true}),recoveredPassword(d));await click(d,'Login');await shown(btn(d,'Quick command'))
    const back=await localPost(d,'/api/users/password/',{current_password:recoveredPassword(d),new_password:d.credentials().password,confirm_password:d.credentials().password});if(!back.ok())throw Error('Demo recovery account restoration failed')
  },true)
]})
