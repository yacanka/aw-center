# Django + Vue Launcher

Kök dizindeki `launcher.py`, repository içindeki Django ve Vue uygulamalarını
keşfeden ince bir komut girişidir. Uygulama adı, Django settings paketi veya
frontend dizini launcher içinde sabit değildir.

## Temel sözleşme

- Launcher `.env`, `.env.local` veya başka bir yapılandırma dosyası oluşturmaz
  ve değiştirmez.
- `.runtime` dizini, PID dosyası veya kalıcı süreç durumu kullanmaz.
- Alt süreçler mevcut shell environment'ını miras alır. Host, port ve
  `VITE_API_URL` yalnız başlatılan süreçlere geçici override olarak verilir.
- `dev` migration uygulamaz; bu davranış yalnız `--migrate` ile açılır.
- İstenen port doluysa launcher başka port seçmez, anlaşılır bir hata ile durur.
- Paketleme Git tarafından izlenen kaynakları esas alır; aktif env dosyalarını,
  private key, virtualenv, runtime ve üretilmiş dosyaları dışarıda bırakır.
  Secretsız `.env.example`/`.env.sample` şablonları pakete alınabilir.
- Offline npm cache hazırlanırken geçici bir install tree kullanılır ve lifecycle
  scriptleri çalıştırılmaz; mevcut `frontend/node_modules` değiştirilmez.

## Komutlar

```bash
python launcher.py setup
python launcher.py check
python launcher.py test
python launcher.py dev --backend-port 8000 --frontend-port 5173
python launcher.py prod --host 0.0.0.0 --backend-port 8000
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
python launcher.py package-changes
```

Her komutun yalnız ilgili parametrelerini görmek için `--help` kullanın:

```bash
python launcher.py dev --help
python launcher.py prod --help
python launcher.py package-offline --help
```

## Production server seçimi

Unix sistemlerde launcher `manage.py` içindeki `DJANGO_SETTINGS_MODULE`
değerinden WSGI import'unu keşfeder ve Gunicorn çalıştırır. Windows veya özel
bir sunucu için shell açmadan ayrıştırılan açık komut verilebilir:

```bash
python launcher.py prod \
  --production-command "{python} -m waitress --listen={host}:{port} {wsgi}"
```

Kullanılabilen placeholder'lar: `{python}`, `{wsgi}`, `{host}`, `{port}`.
TLS, secret, database ve integration ayarları deployment environment'ının
sorumluluğundadır.

## Offline akış

İnternet erişimli makinede bağımlılıkları hazırla ve ZIP oluştur:

```bash
python launcher.py prepare-offline --offline-dir offline
python launcher.py package-offline --offline-dir offline --offline-zip project-offline.zip
```

Offline makinede ZIP'i açıp hazırlanmış paketlerden kur:

```bash
python launcher.py setup --mode offline --offline-dir offline
```
