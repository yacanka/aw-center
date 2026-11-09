export const INITIAL =
  'flowchart LR\n    A(["Bir fikir"]) --> B["Taslağını oluştur"]\n    B --> C{"Hazır mı?"}\n    C -->|Evet| D["Hayata geçir"]\n    C -->|Henüz değil| E["Biraz geliştir"]\n    E --> B'

export const templates = [
  {
    id: 'flowchart',
    label: 'Akış şeması',
    description: 'Bir talebin kontrol, düzeltme ve onay adımlarını gösterir.',
    code: 'flowchart TD\n    A(["Talep alındı"]) --> B["Bilgileri kontrol et"]\n    B --> C{"Bilgiler tam mı?"}\n    C -->|Hayır| D["Eksikleri tamamla"]\n    D --> B\n    C -->|Evet| E["Talebi değerlendir"]\n    E --> F{"Onaylandı mı?"}\n    F -->|Evet| G["İşlemi gerçekleştir"]\n    F -->|Hayır| H["Gerekçeyi bildir"]\n    G --> I(["Tamamlandı"])\n    H --> I'
  },
  {
    id: 'sequence',
    label: 'Sıralama diyagramı',
    description: 'Kullanıcı, uygulama ve veri deposu arasındaki etkileşimi gösterir.',
    code: 'sequenceDiagram\n    autonumber\n    actor K as Kullanıcı\n    participant U as Uygulama\n    participant V as Veri deposu\n    K->>U: Arama ifadesini gönder\n    U->>V: Kayıtları sorgula\n    V-->>U: Sonuçları döndür\n    alt Sonuç bulundu\n        U-->>K: Sonuç listesini göster\n        K->>U: Bir sonuç seç\n        U-->>K: Ayrıntıları aç\n    else Sonuç yok\n        U-->>K: Yeni bir arama öner\n    end'
  },
  {
    id: 'class',
    label: 'Sınıf diyagramı',
    description: 'Sınıfları, özelliklerini, metotlarını ve aralarındaki ilişkileri tanımlar.',
    code: 'classDiagram\n    direction LR\n    class Musteri["Müşteri"]\n    class Siparis["Sipariş"]\n    class Urun["Ürün"]\n    class Musteri {\n        +String ad\n        +siparisVer()\n    }\n    class Siparis {\n        +String durum\n        +float toplam\n        +toplamHesapla()\n    }\n    class Urun {\n        +String ad\n        +float fiyat\n    }\n    Musteri "1" --> "0..*" Siparis : oluşturur\n    Siparis "*" o-- "*" Urun : içerir'
  },
  {
    id: 'er',
    label: 'Varlık ilişki diyagramı',
    description: 'Örnek bir sipariş modelinin tablolarını ve anahtarlarını gösterir.',
    code: 'erDiagram\n    MUSTERI ||--o{ SIPARIS : verir\n    SIPARIS ||--|{ SIPARIS_KALEMI : "içerir"\n    URUN ||--o{ SIPARIS_KALEMI : "kullanılır"\n    MUSTERI {\n        int id PK\n        string ad\n    }\n    SIPARIS {\n        int id PK\n        int musteri_id FK\n        date tarih\n    }\n    URUN {\n        int id PK\n        string ad\n    }\n    SIPARIS_KALEMI {\n        int siparis_id FK\n        int urun_id FK\n        int adet\n    }'
  },
  {
    id: 'state',
    label: 'Durum diyagramı',
    description: 'Bir belgenin taslaktan yayına uzanan durumlarını modeller.',
    code: 'stateDiagram-v2\n    direction LR\n    state "Taslak" as Taslak\n    state "İncelemede" as Inceleme\n    state "Düzeltme bekliyor" as Duzeltme\n    state "Yayımlandı" as Yayin\n    state "Arşivlendi" as Arsiv\n    [*] --> Taslak\n    Taslak --> Inceleme: İncelemeye gönder\n    Inceleme --> Duzeltme: Değişiklik iste\n    Duzeltme --> Inceleme: Yeniden gönder\n    Inceleme --> Yayin: Onayla\n    Yayin --> Arsiv: Arşivle\n    Arsiv --> [*]'
  },
  {
    id: 'gantt',
    label: 'Gantt çizelgesi',
    description: 'Örnek proje görevlerini, sürelerini ve bağımlılıklarını planlar.',
    code: 'gantt\n    title Örnek proje planı\n    dateFormat YYYY-MM-DD\n    axisFormat %d.%m\n    excludes weekends\n    section Hazırlık\n    Gereksinimleri belirle :done, analiz, 2026-11-02, 3d\n    Tasarımı hazırla       :done, tasarim, after analiz, 3d\n    section Uygulama\n    Temel işlevleri geliştir :active, gelistirme, after tasarim, 5d\n    Kontrolleri tamamla      :test, after gelistirme, 3d\n    section Teslim\n    Kullanım notlarını yaz :belge, after gelistirme, 2d\n    İlk sürüm              :milestone, teslim, after test, 0d'
  },
  {
    id: 'pie',
    label: 'Pasta grafiği',
    description: 'Örnek çalışma sürelerinin toplam içindeki dağılımını gösterir.',
    code: 'pie showData\n    title Örnek çalışma dağılımı\n    %% Değerler örnektir ve toplamı 100 eder.\n    "Geliştirme" : 40\n    "Araştırma" : 20\n    "Tasarım" : 15\n    "Test" : 15\n    "Dokümantasyon" : 10'
  },
  {
    id: 'mindmap',
    label: 'Zihin haritası',
    description: 'Bir proje fikrini başlıklara ve alt başlıklara ayırır.',
    code: 'mindmap\n  root((Yeni proje))\n    Amaç\n      Sorunu tanımla\n      Başarı ölçütleri\n    Kullanıcılar\n      İhtiyaçlar\n      Kullanım senaryoları\n    Tasarım\n      Ekranlar\n      Kullanıcı akışı\n    Teslim\n      Görevler\n      Takvim\n      Kontrol listesi'
  },
  {
    id: 'git',
    label: 'Git dallanma grafiği',
    description: 'Bir özellik dalının geliştirilmesini ve ana dala birleştirilmesini gösterir.',
    code: 'gitGraph\n    commit id: "Başlangıç"\n    branch ozellik\n    checkout ozellik\n    commit id: "İlk taslak"\n    commit id: "Kontroller"\n    checkout main\n    commit id: "Belge güncellemesi"\n    merge ozellik id: "Özelliği birleştir"\n    commit id: "İlk sürüm" tag: "v1.0"'
  },
  {
    id: 'timeline',
    label: 'Zaman çizelgesi',
    description: 'Örnek bir ürünün geliştirme aşamalarını dönemlere göre sıralar.',
    code: 'timeline\n    title Örnek ürün yolculuğu\n    section Keşif\n        1. hafta : İhtiyaçları belirle\n                 : Hedefleri netleştir\n        2. hafta : Taslağı hazırla\n    section Geliştirme\n        3. hafta : İlk prototipi tamamla\n        4. hafta : Geri bildirimleri uygula\n    section Yayın\n        5. hafta : Son kontrolleri yap\n                 : İlk sürümü paylaş'
  }
]
