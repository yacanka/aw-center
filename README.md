# AW Center

AW Center; proje bazlı uyumluluk dokümanı yönetimini, JIRA ve mühendislik entegrasyonlarını, Office/PDF araçlarını tek uygulamada birleştirir. Django ve Vue ile geliştirilmiştir.

## Veri güvenliği

AW Center, kullanıcı erişimini ve doküman işlemlerini uygulama sunucusunda denetler:

- **Proje bazlı yetkilendirme:** Görüntüleme ve işlem yapma izinleri, kullanıcının ilgili projedeki rolüne göre kontrol edilir.
- **Oturum koruması:** Kullanıcı oturumları sunucuda yönetilir. Oturum çerezi JavaScript erişimine kapalıdır; veri değiştiren tarayıcı isteklerinde CSRF doğrulaması uygulanır.
- **Korumalı dosya erişimi:** Arka plan işlerinin çıktı dosyaları yalnızca işi başlatan kullanıcıya sunulur. İndirme öncesinde SHA-256 ile dosya bütünlüğü doğrulanır.
- **Dosya yükleme kontrolleri:** Dosya adı, boyutu, uzantısı ve içerik imzası kontrol edilir; arşivlerde açılmış boyut ve dosya yolları da denetlenir.
- **Değişiklik geçmişi:** Uyumluluk dokümanlarındaki değişiklikler geçmiş kayıtlarıyla izlenebilir.
- **Şifreli bağlantı:** Windows production kurulumu HTTPS üzerinden çalışır; tarayıcı ile sunucu arasındaki iletişim TLS ile şifrelenir.

## Gereksinimler

- Python 3.11
- Node.js 22 ve npm
- Kullanılacak doküman araçlarının sistem bağımlılıkları

## Kurulum ve çalıştırma

Windows masaüstü yöneticisi için taşınabilir ZIP'in tamamını çıkarıp
`AWCenterManager.exe` dosyasını açın. Arayüz dev/prod kurulumu, başlatma/durdurma,
kurumsal ve offline kaynaklar ile durum raporlarını yönetir. İlk pencere için
kurulu Python, Node veya Git gerekmez. ZIP, Windows build workflow'u tarafından
üretilir; kaynak `.pyw` dosyası taşınabilir EXE'nin yerine geçmez.
[Masaüstü yöneticisi rehberi](docs/windows-manager.md) paketleme ve kullanımı açıklar.

Terminal akışı `AWCenter.cmd` ile kullanılabilir.
[Windows CLI yardımcısı](docs/windows-install-helper.md) ayrıntıları açıklar.

Mevcut Python/Node kurulumu olan development ortamlarında aşağıdaki düşük seviyeli
launcher akışı da kullanılabilir.

Bağımlılıkları kurun:

```bash
python launcher.py setup
```

Ortam yapılandırmasını tamamlayıp uygulamayı başlatın:

```bash
python launcher.py check
python launcher.py dev --migrate
```

Sonraki çalıştırmalarda `python launcher.py dev` yeterlidir. Yeni migration varsa `--migrate` ekleyin. Launcher, uygulama ile arka plan işlerini birlikte başlatır.

Varsayılan adresler:

- Uygulama: http://127.0.0.1:5173/app/
- API: http://127.0.0.1:8000/api/

## Kontroller

```bash
python launcher.py check
python launcher.py test
npm --prefix frontend run build
```

## Windows production

Güncel production kurulumu Windows üzerinde `launcher.py prod` ile çalışır. Kurulum adımları için [deployment rehberini](docs/deployment.md) izleyin.

```bash
python launcher.py prod --help
```

## Proje yapısı

- `backend/`: Django API, iş akışları ve entegrasyonlar
- `frontend/src/`: Vue arayüzü
- `scripts/launcher/`: kurulum ve çalıştırma araçları
- `docs/`: teknik dokümantasyon

## Dokümantasyon

- [Mimari](docs/architecture.md)
- [Launcher ve çevrimdışı kurulum](docs/launcher-runtime.md)
- [Test stratejisi](docs/testing-strategy.md)
- [Windows DOORS otomasyonu](docs/doors-worker.md)

Yönetim raporları, haftalık snapshot karşılaştırması ve özel PDF indirme için [Management Reports](docs/management-reports.md) rehberini kullanın.
