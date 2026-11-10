"""Set up fictional inputs used in the supplementary recordings."""
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'backend_demo'))
from run import STATE,prepare

def main(action):
    generation=prepare(False)
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from docx import Document
    assert Path(settings.DATABASES['default']['NAME'])==generation/'demo.sqlite3'
    if action=='revision':
        doc=Document()
        doc.add_heading('Taslak kontrol yönergesi',0)
        doc.add_paragraph('Ön taslakta henüz onaylanmamış ek terimler yer alır.')
        doc.save(STATE/'examples'/'taslak.docx')
    elif action=='release':
        from releases.models import ReleaseNoteSeen
        ReleaseNoteSeen.objects.filter(user=get_user_model().objects.get(username='D10003'),release_note__version='1.0.0-demo').delete()
    elif action=='attention':
        from attention.models import ActionCenterDecision
        ActionCenterDecision.objects.filter(user__username='D10001').delete()
    elif action=='verify-reset':
        from orgs.models import Project
        assert generation.name.startswith('state-')
        assert Project.objects.filter(slug='gokbey',name='Atlas Demo Projesi').exists()
        assert get_user_model().objects.filter(username='D10001',is_superuser=True).exists()
    else:raise ValueError('Unknown recording setup')
if __name__=='__main__':main(sys.argv[1])
