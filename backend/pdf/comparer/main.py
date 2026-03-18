#!/usr/bin/env python3
"""
PDF Karşılaştırıcı Pro - Ana Uygulama

Kullanım:
    python main.py                      # GUI modunda başlat
    python main.py --cli file1 file2    # Komut satırı modunda
"""

import sys
import argparse
from pathlib import Path


def run_gui():
    """GUI modunda çalıştır"""
    from gui.main_window import MainWindow
    app = MainWindow()
    app.run()


def run_cli(file1: str, file2: str, output: str = None):
    """Komut satırı modunda çalıştır"""
    from text_comparator import PDFComparator, ComparisonOptions
    from report_generator import HTMLReportGenerator
    
    print("🔍 PDF Karşılaştırıcı Pro - CLI Modu")
    print("=" * 50)
    
    if not Path(file1).exists():
        print(f"❌ Dosya bulunamadı: {file1}")
        sys.exit(1)
    if not Path(file2).exists():
        print(f"❌ Dosya bulunamadı: {file2}")
        sys.exit(1)
    
    print(f"📄 Dosya 1: {file1}")
    print(f"📄 Dosya 2: {file2}")
    print()
    print("⏳ Karşılaştırılıyor...")
    
    try:
        comparator = PDFComparator()
        result = comparator.compare(file1, file2)
        
        summary = result.summary
        print()
        print("📊 Sonuçlar:")
        print("-" * 30)
        print(f"  Benzerlik:     {summary['similarity']}")
        print(f"  Eklenen:       +{summary['additions']} satır")
        print(f"  Silinen:       -{summary['deletions']} satır")
        print(f"  Değişen:       ~{summary['modifications']} satır")
        print(f"  Toplam Sayfa:  {summary['total_pages_1']} / {summary['total_pages_2']}")
        
        if output:
            print()
            print(f"📝 HTML rapor oluşturuluyor: {output}")
            generator = HTMLReportGenerator()
            generator.save_report(result, output)
            print("✅ Rapor oluşturuldu!")
        
        print()
        print("✅ Karşılaştırma tamamlandı!")
        
    except Exception as e:
        print(f"❌ Hata: {str(e)}")
        sys.exit(1)


def main():
    """Ana fonksiyon"""
    parser = argparse.ArgumentParser(
        description="PDF Karşılaştırıcı Pro - Gelişmiş PDF karşılaştırma aracı"
    )
    
    parser.add_argument("--cli", action="store_true", help="Komut satırı modunda çalıştır")
    parser.add_argument("files", nargs="*", help="Karşılaştırılacak PDF dosyaları")
    parser.add_argument("-o", "--output", help="HTML rapor çıktı dosyası")
    
    args = parser.parse_args()
    
    if args.cli:
        if len(args.files) != 2:
            print("❌ CLI modunda 2 dosya belirtmelisiniz!")
            print("Kullanım: python main.py --cli dosya1.pdf dosya2.pdf")
            sys.exit(1)
        run_cli(args.files[0], args.files[1], args.output)
    else:
        run_gui()


if __name__ == "__main__":
    main()
