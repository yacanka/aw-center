# Özel geliştirme ortamı ve anahtar geçişi

`DEBUG=True` olsa da açık `SECRET_KEY` zorunludur. JIRA etkinse bağımsız bir
`JIRA_SESSION_ENCRYPTION_KEY` gerekir. Eksik/geçersiz anahtar başlangıcı durdurur;
ortak geliştirme anahtarı veya Django anahtarından türetilen JIRA anahtarı yoktur.
`launcher.py setup` yalnız bağımlılıkları kurar; hiçbir başlangıç akışı anahtar yazmaz.

## Yeni kurulum

Önce repository kökünde `python launcher.py setup` çalıştırın. Gerçek yapılandırma
repository, OneDrive ve network share dışında, kurumun izin verdiği yerel alanda
tutulmalıdır. Development ve production dosyaları/anahtarları ayrı olmalıdır.

### macOS ve Linux dizin izinleri

macOS için:

```bash
export AWCENTER_PRIVATE_CONFIG_DIR="$HOME/Library/Application Support/AWCenter/config"
mkdir -p "$AWCENTER_PRIVATE_CONFIG_DIR"
chmod -N "$AWCENTER_PRIVATE_CONFIG_DIR"
chmod 700 "$AWCENTER_PRIVATE_CONFIG_DIR"
ls -lde "$AWCENTER_PRIVATE_CONFIG_DIR"
```

`ls -lde` çıktısında numaralı ACL girdisi olmamalıdır. macOS'ta yalnız sayısal
`chmod` genişletilmiş allow/inherit ACL'lerini kaldırmaz; `chmod -N` bunları temizler.
Linux için dizini `${XDG_CONFIG_HOME:-$HOME/.config}/AWCenter` seçin ve macOS'a özgü
`chmod -N`/`ls -lde` adımlarını kullanmayın. Dizin sahibi mevcut kullanıcı olmalı;
dizin symlink olmamalıdır.

### Windows dizin ACL sınırı

PowerShell'i AW Center'ı çalıştıracak kullanıcıyla açın. Aşağıdaki işlem config
dizininin ACL'sini bu kullanıcıyla sınırlar; mevcut ortak config dizininde farklı
hesaplar çalışıyorsa onların erişimini kaldırmadan önce ayrı bir dizin seçin.

```powershell
$env:AWCENTER_PRIVATE_CONFIG_DIR = Join-Path $env:LOCALAPPDATA 'AWCenter\config'
New-Item -ItemType Directory -Path $env:AWCENTER_PRIVATE_CONFIG_DIR -Force | Out-Null
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = [System.Security.AccessControl.DirectorySecurity]::new()
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)
$rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
    $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'
)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $env:AWCENTER_PRIVATE_CONFIG_DIR -AclObject $acl
$actual = Get-Acl -LiteralPath $env:AWCENTER_PRIVATE_CONFIG_DIR
if (-not $actual.AreAccessRulesProtected -or @($actual.Access).Count -ne 1 -or
    $actual.Access[0].IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]) -ne $sid -or
    $actual.Access[0].AccessControlType -ne 'Allow' -or $actual.Access[0].IsInherited) {
    throw 'Private directory ACL verification failed.'
}
```

Windows'ta `chmod` tek başına gizlilik kanıtı değildir. Yerel yöneticilerin sahiplik
alabilmesi işletim sistemi yetkisidir; bu ACL normal diğer kullanıcıların erişimini
sınırlar. Config dosyası oluşturulduktan sonra da `Get-Acl` ile yalnız seçilen SID'nin
kalıtılan izinlere sahip olduğunu kontrol edin.

### Dosyayı bir kez oluşturma

Repository kökünden `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`)
yorumlayıcısına aşağıdaki Python bloğunu verin; örneğin POSIX'te
`.venv/bin/python - <<'PY'` ve Windows'ta PowerShell here-string ile
`@' ... '@ | .venv\Scripts\python.exe -` kullanın. Kod mevcut dosyaları ezmez,
anahtarları terminale yazmaz ve yeni bir CLI gerektirmez.

```python
import os
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from cryptography.fernet import Fernet

root = Path.cwd().resolve()
directory = Path(os.environ["AWCENTER_PRIVATE_CONFIG_DIR"]).expanduser()
if directory.is_symlink() or directory.resolve().is_relative_to(root):
    raise SystemExit("Use a private directory outside the checkout.")
if os.name != "nt":
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SystemExit("The private directory must be owner-only (0700).")
if sys.platform == "darwin":
    acl = subprocess.check_output(["ls", "-lde", str(directory)], text=True)
    if len(acl.splitlines()) != 1:
        raise SystemExit("Remove macOS extended ACLs before creating keys.")
target = directory / "development.env"
pointer = root / "backend/.env"
if pointer.exists() or pointer.is_symlink():
    raise SystemExit("Existing setup: follow the migration procedure below.")
source = (root / "backend/.env.example").read_text(encoding="utf-8")
lines = [line for line in source.splitlines() if not line.startswith(
    ("SECRET_KEY=", "JIRA_SESSION_ENCRYPTION_KEY=", "AWCENTER_ENV_FILE=")
)]
lines += ["SECRET_KEY=" + secrets.token_urlsafe(64),
          "JIRA_SESSION_ENCRYPTION_KEY=" + Fernet.generate_key().decode("ascii")]
with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
               "w", encoding="utf-8") as output:
    output.write("\n".join(lines) + "\n")
with os.fdopen(os.open(pointer, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
               "w", encoding="utf-8") as output:
    output.write(f'AWCENTER_ENV_FILE="{target.as_posix()}"\n')
```

POSIX'te dosya modu `0600` olmalıdır. macOS'ta oluşturulan dosyayı da `ls -le` ile
kontrol edin; numaralı ACL girdisi bulunmamalıdır. Windows'ta dosyanın DACL'sinde
yalnız yukarıdaki kullanıcı SID'sine izin verildiğini doğrulayın. Gerçek dosyayı,
anahtarlarını veya içeriğini Git'e, loglara, ekran görüntülerine, sohbetlere ve
offline/release paketlerine koymayın.

`AWCENTER_ENV_FILE` process environment'da verilirse `backend/.env` yerine o dosya
seçilir. Aksi halde `backend/.env` işaretçisi okunur. Process değerleri dosyadan
daha yüksek önceliklidir; seçilen harici dosya tüm gerekli ayarları içermelidir.
Göreli database/artifact/model yollarının anlamı config dosyasının konumuna taşınmaz;
mevcut backend çalışma dizini ve settings çözümlemesi korunur.

## Mevcut kurulumun geçişi

1. Web ve worker'ları kontrollü durdurun; çalışan işlerin tamamlanmasını bekleyin.
2. Etkin `.env`/seçili profil ve process override'larını değerleri yazdırmadan
   inceleyin. Mevcut ayarları yeni dosyaya koruyarak taşıyın; boş örnek dosyayla
   değiştirip entegrasyonları, database veya artifact yollarını kaybetmeyin.
3. Yukarıdaki üretim yöntemini kullanarak iki bağımsız anahtarı yalnız özel dosyada
   yenileyin. Aynı dosyayı tekrar üretmeyin; normal yeniden başlatmalarda anahtarlar
   kalıcıdır. Eski process override'ları varsa yenileyin veya kaldırın.
4. Dosya izinlerini/ACL'yi ve ayar eşdeğerliğini doğruladıktan sonra `backend/.env`
   dosyasını yalnız harici dosyayı gösteren `AWCENTER_ENV_FILE` satırına dönüştürün.
5. `python launcher.py check` çalıştırın, web/worker'ları aynı profille başlatın.
   AW Center'a ve JIRA'ya tekrar giriş yapın. Kayıtları veya dosyaları silmeyin.

Eski anahtarı `SECRET_KEY_FALLBACKS` içinde tutmayın. Eski Django oturumları ve
imzalı reset/davet bağlantıları geçersizleşir; gerektiğinde yeni bağlantı isteyin.
Eski reset outbox kayıtları state digest uyuşmazlığında gönderilmeden iptal edilir;
yeni reset isteği oluşturulabilir. JIRA'nın eski şifreli geçici bağlantısı okunamazsa
yalnız o cache girdisi temizlenir; yeniden bağlantı kurulabilir. Kullanıcı parolaları,
tercihler, iş verileri ve private artifact'lar anahtar geçişinde silinmez.

## Doğrulama

- Anahtarların değerlerini göstermeden yapılandırmanın açık, geçerli ve iki süreçte
  aynı olduğunu kontrol edin. Anahtar eksikken başlangıç reddedilmelidir.
- Development ve production state yollarını birbirine yönlendirmeyin.
- CI test anahtarları yalnız disposable ortamlar içindir; gerçek kurulumda kullanılmaz.
- Windows CI private config smoke'u NTFS DACL'yi ve iki ayrı settings import'unu
  doğrular. macOS sonucu Windows üzerinde çalıştırılmış doğrulama yerine geçmez.

## DCC reviewer configuration

The existing Gokbey DCC rule also needs `GOKBEY_DCC_POLICY_FILE`, an absolute path
to an owner-restricted external JSON file. The names belong in that file, not in
this document, the source tree or tests. See [private DCC policy](dcc-private-policy.md)
for the exact schema, POSIX/Windows permissions and DocProof CA setup.

## Private workflow mappings

Project integration metadata, cover-page work-package labels and the approved
DDF explanation are provisioned through `PROJECT_CONFIGURATION_FILE` and
`DDF_ASSESSMENT_POLICY_FILE`. See [private workflow configuration](private-workflow-configuration.md)
for schemas, permissions and coordinated deployment. These files do not define
capabilities, grant project roles or modify existing records.
