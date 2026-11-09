from datetime import datetime, time, timedelta
import json
from uuid import NAMESPACE_DNS, uuid5
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.db import transaction

from compliance.models import ComplianceDocument, CoverPage, DocumentStatus, ReviewTask
from compliance.services import request_review, set_archive_state, transition_document
from ddf.models import DDF
from orgs.models import Project, ProjectRoleAssignment, Panel, Person, ResponsibleAssignment
from releases.models import ReleaseNote, ReleaseNoteItem, ReleaseNoteSeen
from examples import REFERENCE, source_title, write_examples


def identifier(key):
    return uuid5(NAMESPACE_DNS, f'aw-center-video.example.invalid/{key}')


def seed(state):
    import jira_demo
    samples = state / 'examples'
    write_examples(samples)
    with transaction.atomic():
        accounts = json.loads((state / 'access.json').read_text())
        users = []
        for i, first in enumerate(['Deniz', 'Ada', 'Ekin', 'Ilgın', 'İpek', 'Bora']):
            username = f'D{10001+i}'
            user = User.objects.create_user(username, email=f'{username.lower()}@example.invalid', password=accounts['password'], first_name=first, last_name='Örnek', is_staff=i==0, is_superuser=i==0)
            user.preferences.theme = 'light'
            user.preferences.language = 'tr'
            user.preferences.items_per_page = 10
            user.preferences.save()
            users.append(user)
        admin, viewer, editor = users[:3]
        projects = list(Project.objects.order_by('id'))
        for project in projects:
            if project.slug == 'gokbey':
                project.name = 'Atlas Demo Projesi'
            elif project.slug == 'ozgur':
                project.name = 'Deniz Demo Projesi'
            else:
                project.name = f'Örnek Çalışma {project.id:02}'
                project.enabled = False
            project.save()
        main = Project.objects.get(slug='gokbey')
        group = Group.objects.create(name='Belge Kontrol Ekibi')
        editor.groups.add(group)
        for domain, role in [('compliance','editor'),('organization','manager'),('jira','operator')]:
            ProjectRoleAssignment.objects.create(project=main, group=group, domain=domain, role=role)
            ProjectRoleAssignment.objects.create(project=main, user=viewer, domain=domain, role='viewer')
        panels = []
        for n, name in enumerate(['Belge Yönetimi', 'Kalite ve Süreç', 'Kayıt Kontrolü', 'Yayın Koordinasyonu']):
            panel = Panel.objects.create(project=main, name=name, ata=f'{21+n}-00', discipline=name)
            panels.append(panel)
        for index, user in enumerate(users):
            person = Person.objects.create(person_id=user.username, name=user.get_full_name(), email=user.email)
            for n, panel in enumerate(panels):
                ResponsibleAssignment.objects.create(panel=panel, person=person, responsibility_role=['AS','CVE','IPT','PCE'][(index+n)%4])
        make_docs(main, panels, admin, editor)
        DDF.objects.create(project=main.name, doc_name='Belge yönetim planı',doc_no='ATL-DOK-001',doc_issue='A',date='2026-11-02',commentor=editor.get_full_name(),comments=[['1','Kalite','Belge onay alanı eksik.','Güncelleme planlandı.','Açık','Bölüm 3']],comment_types=[],created_by=admin)
        note = ReleaseNote.objects.create(version='1.0.0-demo', title='Atlas çalışma alanı', requires_ack=False)
        ReleaseNoteItem.objects.create(release_note=note,item_type='feature',heading='Doküman kaydı',body_md='Atlas örnek dokümanlarını ve kontrol listelerini proje alanından inceleyebilirsiniz.')
        ReleaseNoteSeen.objects.create(release_note=note,user=admin)
        jira_demo.seed(admin, editor, main, samples)
    seed_jobs(admin, samples)


def make_docs(project, panels, admin, editor):
    statuses = [('to_be_issued','Yayına hazırlanıyor'),('airworthiness_review','Teknik incelemede'),('authority_review','Onayda'),('to_be_updated','Güncelleme bekliyor'),('authority_approved','Onaylandı')]
    for key, label in statuses:
        DocumentStatus.objects.create(id=identifier(f'status-{key}'),project=project,value=key,label=label)
    for n in range(1, 37):
        start = REFERENCE - timedelta(days=26+n%10)
        target = REFERENCE + timedelta(days=n%21-8)
        issued = n%5 in [0,4]
        cover = CoverPage.objects.create(id=identifier(f'cover-{n}'),project=project,number=f'ATL-KP-{n:03}',issue='B' if issued else 'A')
        doc = ComplianceDocument.objects.create(id=identifier(f'document-{n}'),project=project,panel=panels[(n-1)%len(panels)],cover_page=cover,name=source_title(n),number=f'ATL-DOK-{n:03}',issue=cover.issue,cat=str(1+n%3),moc=str(n%5),requirements=[f'ATL-GER-{n:03}'],target_date=target, release_date=(REFERENCE-timedelta(days=n%4)) if issued else None,owner=admin if n%3 else editor, responsible=editor.get_full_name(), notes='Atlas Demo Projesi için hazırlanan örnek kayıt.',created_at=datetime.combine(start,time(10),ZoneInfo('Europe/Istanbul')))
        sequence = [statuses[0][0]]
        if n%5: sequence.append(statuses[n%5][0])
        for index, status in enumerate(sequence):
            doc,_ = transition_document(project=project,document_id=doc.id,expected_version=doc.version,new_status=status,effective_date=start+timedelta(days=index*7),next_action_due_date=None if issued else target,reason=['Belge kayıt planına alındı.','İnceleme kaydı güncellendi.'][index],user=admin)
        if n in [2,3,7]:
            request_review(project=project,document_id=doc.id,expected_version=doc.version,kind=ReviewTask.Kind.REVIEW,assignee=admin,due_date=target,request_note='Revizyon bilgisini ve ekleri inceleyin.',user=editor)
        if n == 36:
            set_archive_state(project=project,document_id=doc.id,expected_version=doc.version,archived=True,reason='Önceki plan arşivlendi.',user=admin)


def seed_jobs(owner, samples):
    from jobs.services import create_job, request_cancellation, set_job_state
    from jobs.models import JobStatus
    from jobs.worker import claim_next_job, execute_claimed_job
    from worker import executor
    from jobs.execution import remove_worker
    def create(kind, title, filename, parameters):
        upload = ContentFile((samples/filename).read_bytes(), name=filename)
        return create_job(owner=owner, kind=kind, title=title, parameters=parameters,uploaded_file=upload,idempotency_key=f'sample-{kind}')[0]
    job = create('excel.cover_pages','Atlas kapak sayfaları','cover.xlsx',{})
    claim = claim_next_job('seed:atlas', (job.kind,))
    execute_claimed_job(claim,executor)
    job.refresh_from_db()
    assert job.status == 'succeeded', (job.kind, job.error_code)
    remove_worker('seed:atlas')
    job = create('word.translate','Önceki çeviri isteği','atlas.docx',{'translate_type':'tr2en'})
    request_cancellation(job)
