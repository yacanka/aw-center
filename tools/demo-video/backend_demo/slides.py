"""Build the two-slide file in an interpreter with python-pptx installed."""
import sys
from pptx import Presentation


def main(path):
    pres = Presentation()
    for title, points in [('Belge yönetim planı',['Atlas Demo Projesi','ATL-DOK-001 · B revizyonu']),('İnceleme akışı',['Belge sorumlusu revizyonu açar.','İkinci göz kayıtları kontrol eder.','Onaylı belge arşive alınır.'])]:
        slide = pres.slides.add_slide(pres.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = '\n'.join(points)
    pres.save(path)

if __name__ == '__main__':
    main(sys.argv[1])
