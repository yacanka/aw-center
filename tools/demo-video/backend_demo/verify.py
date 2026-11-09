"""Check the isolated Django stack against real HTTP and artifact contracts."""
import hashlib
import json
import socket
from io import BytesIO
from zipfile import ZipFile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document
from rest_framework.test import APIClient

from jobs.execution import touch_worker
from jobs.models import Job
from jobs.worker import claim_next_job, execute_claimed_job
from worker import executor


def verify(state,generation):
    assert str(generation) in str(settings.DATABASES['default']['NAME'])
    assert str(generation) in str(settings.PRIVATE_MEDIA_ROOT)
    assert settings.AWCENTER_MAIL_TRANSPORT == 'disabled' and 'locmem' in settings.EMAIL_BACKEND
    try:
        socket.create_connection(('192.0.2.1',443),timeout=.1)
    except PermissionError:
        pass
    else:
        raise AssertionError('Egress must fail before DNS or connection.')
    client = APIClient(enforce_csrf_checks=True)
    login = json.loads((state/'access.json').read_text())
    client.get('/api/session/')
    csrf = client.cookies['csrftoken'].value
    assert client.post('/api/session/',{'username':login['admin'],'password':login['password']},format='json').status_code == 403
    response = client.post('/api/session/',{'username':login['admin'],'password':login['password']},format='json',HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200,response.status_code
    csrf = client.cookies['csrftoken'].value
    touch_worker('doors-worker:atlas-demo')
    samples = state/'examples'

    def post(path,values,code=200,file=None):
        extra = {'HTTP_X_CSRFTOKEN':csrf,'HTTP_IDEMPOTENCY_KEY':f'probe-{path.rsplit("/",2)[-2]}'}
        if file:
            values = {**values,'file':SimpleUploadedFile(file,(samples/file).read_bytes(),content_type='application/octet-stream')}
        response = client.post('/api/'+path,values,format='multipart' if file else 'json',**extra)
        assert response.status_code == code, (path,response.status_code,response.content[:250])
        return response.json()

    def completed(job):
        assert client.get(f"/api/jobs/{job['id']}/download/").status_code != 200
        claim = claim_next_job('doors-worker:atlas-demo',(job['kind'],))
        assert str(claim.id) == job['id']
        execute_claimed_job(claim,executor)
        claim.refresh_from_db()
        assert claim.status=='succeeded',(claim.kind,claim.error_code)
        down = client.get(f'/api/jobs/{claim.id}/download/')
        assert down.status_code==200
        data = b''.join(down.streaming_content)
        assert hashlib.sha256(data).hexdigest() == claim.output_sha256
        return data

    report = post('integrations/assistant/chat/',{'message':'Bir işin ilerleme durumunu nerede görebilirim?','current_path':'/jobs'})
    assert report['answer'] and report['sources']
    assert client.get('/api/integrations/docproof/search/',{'document_no':'ATL-DOK-001'}).json()==1
    assert client.get('/api/integrations/teamcenter/status/').json()['configured']
    assert post('integrations/teamcenter/probe/',{})['connected']
    row = {'object':{'uid':'UID-1','type':'WorkspaceObject'},'properties':{'object_name':['İncelenen örnek']}}
    completed(post('integrations/teamcenter/property-update-jobs/',{'updates':[row]},201))
    assert post('integrations/teamcenter/objects/load/',{'uids':['UID-1']})['ServiceData']['modelObjects']['UID-1']['props']['object_name']==['İncelenen örnek']
    doors = json.loads(completed(post('integrations/doors/module-export-jobs/',{'module_path':'/Atlas/Belgeler','limit':25},201)))
    assert doors['results'][0]['attributes']['Name']=='Dosya kabulü'
    assert json.loads(completed(post('integrations/doors/module-quality-jobs/',{'module_path':'/Atlas/Belgeler'},201)))['operation_result']['outcome']=='success'
    analysis = json.loads(completed(post('tools/word/jobs/analyze/',{},201,file='atlas.docx')))
    assert len(analysis['checks'])==5 and any(c['evidence'] for c in analysis['checks'])
    assert len([c for c in analysis['checks'] if c['status']=='error'])==1
    translated = completed(post('tools/word/jobs/translate/',{'translate_type':'tr2en'},201,file='atlas.docx'))
    assert Document(BytesIO(translated)).paragraphs[0].text=='Atlas document management plan'
    assert json.loads(completed(post('tools/presentations/presentations/upload/',{},201,file='atlas.pptx')))['slide_count']==2
    cover = next(job for job in Job.objects.filter(kind='excel.cover_pages', status='succeeded'))
    with cover.output_file.open('rb') as source, ZipFile(source) as archive:
        assert len(archive.namelist())==3
        assert all(Document(BytesIO(archive.read(name))).tables for name in archive.namelist())
    other = APIClient()
    other.force_authenticate(User.objects.get(username=login['viewer']))
    assert other.get(f'/api/jobs/{cover.id}/download/').status_code == 404
    print('Verified isolated session/CSRF, external connection denial, owner isolation, cover archive, Word translation and analysis, DOORS export/quality, persistent Teamcenter writes, assistant, DocProof and presentation receipt.')
