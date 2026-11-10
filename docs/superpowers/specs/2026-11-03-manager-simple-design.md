# AW Center Manager sade yönetim

Kullanıcı, 03.11.2026 tarihinde sunulan üç örnek arasından **Sade yönetim**
yerleşimini seçti ve mevcut `AWCenterManager` penceresine uygulanmasını istedi.

## Kapsam ve yaklaşım

- Mevcut Tkinter/ttk penceresini koru; yeni GUI framework veya bağımlılık ekleme.
- Operasyon paneli ve kurulum sihirbazı alternatifleri seçilmedi.
- Üç sekme: Çalışma, Paket kaynakları, Durum ve rapor.
- Çalışma sekmesinde seçili işlemin gerçek durumunu gösteren özet, temel profil
  ayarları ve ilgili eylemler bulunur. İşlem listesi ayarlardan sonra aynı
  kaydırılan Çalışma akışında kalır; alt çubuktan diğer sekmelerden erişilebilir.
- Kaynak dizini, host ve backend portu görünürdür. Frontend portu, Python,
  `.env`, TLS ve migration seçenekleri açılır gelişmiş ayarlardadır.
- Üretim seçimi ve gelişmiş alan doğrulama hataları ilgili alanları görünür yapar.
- Paket işlemleri kendi sekmesinde bulunur; seçili işlemi durdurma tüm sekmelerde
  erişilebilir kalır. Rapor, tarayıcı açma ve klavye kısayolları korunur.
- Tipografi, boşluklar ve ana eylem vurgusu sadeleştirilir; yüzeyler ve metinler
  onaylanan örneğin açık/koyu paletini kullanır. Sistem font ailesi ve DPI
  korunurken 13/25/16 px metin rolleri, 42 px durum simgesi, 30 px içerik hizası,
  16 px alan aralığı ve 7/6 px düğme/alan köşeleri referans alınır.
  Advanced SystemCare fikri kontrol durumu ve durum vurgusuyla sınırlıdır;
  ayrı bir IObit kopyası veya yeni ürün paleti oluşturulmaz.

## Korunacak davranış

Görev seçimi, bağımsız süreçler, owner-scoped rapor, güvenli indirme/URL,
Python ve `.env` seçimi, isteğe bağlı migration, iptal ve nonmodal yönetici
penceresi değişmez. Form düzenlemek çalışan görevin durumunu veya seçeneklerini
değiştirmez. Controller temizliği bitmeden görev tamamlanmış ilan edilmez.
Önizlemedeki örnek durumlar veya adresler uygulamaya taşınmaz.

## Doğrulama

Gelişmiş alan görünürlüğü, hata odağı ve seçili görev özetine headless testler;
gerçek ttk widget'larına native testler eklenir. Manager test grubu ve ilgili
launcher testleri çalıştırılır. Windows EXE/paket görsel kabulü Windows gerektirir.
