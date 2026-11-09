"""Narrow synthetic providers. The normal endpoints, validations and job lifecycle run."""
import ast
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.conf import settings


@contextmanager
def store():
    db = sqlite3.connect(Path(os.environ['AW_DEMO_GENERATION'])/'providers.sqlite3', timeout=10)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS entries (domain TEXT, ident TEXT, data TEXT, PRIMARY KEY(domain,ident))')
            yield db
    finally:
        db.close()


def saved(db, domain, key, default):
    row = db.execute('SELECT data FROM entries WHERE domain=? AND ident=?',(domain,key)).fetchone()
    return json.loads(row[0]) if row else default


def save(db, domain, key, value):
    db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?)',(domain,key,json.dumps(value,ensure_ascii=False)))


class Doors:
    MODULES = ('/Atlas/Belgeler','/Atlas/Gereksinimler')
    COLUMNS = ['Name','Cover Page Number','Number','Issue','Object Heading','Object Text','ATA Chapter','Panel','PoC','Requirement','Discipline','Applicable Disciplines']

    def check_module(self, path):
        return SimpleNamespace(ok=path in self.MODULES)

    def rows(self, db, path):
        from integrations.doors.exceptions import DoorsOperationError
        if not self.check_module(path).ok:
            raise DoorsOperationError('Demo modülü bulunamadı.', 'OPEN_MODULE')
        fixture = [{ 'Name':name,'Cover Page Number':f'ATL-IMP-{i:03}', 'Number':f'ATL-IMP-D{i:03}','Issue':'A','Object Heading':name, 'Object Text':f'{name} için belge kanıtı kayda alınmalıdır.','ATA Chapter': ['21','22','22','24'][i-1],'Panel':['Belge Yönetimi','Kalite','Belge Kontrolü',''][i-1],'PoC':f'ATL-P-{i:02}', 'Requirement':f'ATL-GER-{i:03}', 'Discipline':'Belge Kontrolü','Applicable Disciplines':'Belge Kontrolü'} for i,name in enumerate(['Dosya kabulü','Revizyon takibi','İçerik denetimi','Yayın kontrolü'],1)]
        return saved(db,'doors',path,fixture)

    def list_objects(self,path,attributes,loop,limit):
        from integrations.doors.models import DoorsObject
        with store() as db:
            return [DoorsObject(i, f'ATL-{i:03}',1,{name:data.get(name,'') for name in attributes}) for i,data in enumerate(self.rows(db,path)[:limit],1)]

    def get_object(self,path,absolute_number,attributes):
        from integrations.doors.exceptions import DoorsOperationError
        rows = self.list_objects(path,attributes,'full',10000)
        if not 1 <= absolute_number <= len(rows):
            raise DoorsOperationError('Örnek nesne bulunamadı.','FIND_OBJECT')
        return rows[absolute_number-1]

    def list_attributes(self,path):
        with store() as db:
            return list(dict.fromkeys(k for row in self.rows(db,path) for k in row))

    def export_module(self,path,limit):
        columns = self.list_attributes(path)
        rows = self.list_objects(path,columns,'full',limit+1)
        return {'columns':columns,'results':[r.to_dict() for r in rows[:limit]],'truncated':len(rows)>limit,'attributes_truncated':False}

    def check_applicable_disciplines(self,path):
        return self.list_objects(path,['Applicable Disciplines','Discipline'],'full',100)

    def set_object_attributes(self,path,number,attributes):
        self.get_object(path,number,[])
        with store() as db:
            rows = self.rows(db,path)
            rows[number-1].update(attributes)
            save(db,'doors',path,rows)

    def create_object(self,path,position,relative,attributes):
        with store() as db:
            rows = self.rows(db,path)
            rows.append(dict(attributes))
            save(db,'doors',path,rows)
        return self.get_object(path,len(rows),list(attributes))

    def link_requirements(self,values):
        with store() as db:
            refs = self.rows(db,values['ref_module_name'])
            targets = self.rows(db,values['target_module_name'])
            links = set(saved(db,'links',values['link_module_name'],[]))
            groups, missing, matches = [], [], []
            for row in refs:
                poc = row.get(values['ref_attr_poc'],'')
                req = row.get(values['ref_attr_req'],'')
                if not poc or not req:
                    continue
                found = any(t.get(values['target_attr_poc']) == poc for t in targets)
                groups.append({'poc':poc,'requirements':[req],'target_found':found})
                if found:
                    matches.append(f"{values['direction']}|{req}|{poc}")
                else:
                    missing.append(poc)
            existing = len(links.intersection(matches))
            created = len(set(matches)-links) if values['activeness'] else 0
            if values['activeness']:
                save(db,'links',values['link_module_name'],sorted(links.union(matches)))
            return {'type':'doors_requirement_linker','schema_version':1,'mode':'link' if values['activeness'] else 'preview','direction':values['direction'],'summary':{'reference_objects':len(refs),'groups':len(groups),'candidates':len(groups),'matched_targets':len(matches),'missing_targets':len(missing),'created_links':created,'existing_links':existing},'groups':groups,'missing_targets':missing}


class Teamcenter:
    config = SimpleNamespace(service_root='RestServices')

    def find_saved_queries(self):
        return {'savedQueries':[{'name':'Atlas belge kayıtları','query':{'uid':'ATLAS-Q1','type':'ImanQuery'}}]}

    def execute_saved_query(self,uid,entries,values,maximum):
        ids = ['UID-1','UID-2'] if uid == 'ATLAS-Q1' else []
        return {'arrayOfResults':[{'objectUIDS':ids[:maximum]}]}

    def load_objects(self,uids):
        with store() as db:
            objects = {uid:{'uid':uid,'type':'WorkspaceObject','props':saved(db,'teamcenter',uid,{'object_name':[name],'revision':['B']})} for uid,name in [('UID-1','Atlas belge yönetim planı'),('UID-2','İnceleme listesi')] if uid in uids}
            return {'ServiceData':{'modelObjects':objects}}

    def get_properties(self,objects,names):
        result = self.load_objects([o.uid for o in objects])
        for item in result['ServiceData']['modelObjects'].values():
            item['props'] = {k:v for k,v in item['props'].items() if k in names}
        return result

    def set_properties(self,updates):
        from integrations.teamcenter.exceptions import TeamcenterServiceError
        for model, edits in updates.items():
            current = self.load_objects([model.uid])['ServiceData']['modelObjects'].get(model.uid)
            if not current:
                raise TeamcenterServiceError('Demo nesnesi bulunamadı.')
            with store() as db:
                current['props'].update({edit.name:list(edit.values) for edit in edits})
                save(db,'teamcenter',model.uid,current['props'])


def docproof(value):
    from compliance.models import ComplianceDocument
    row = ComplianceDocument.objects.filter(number__iexact=value).first()
    return (1 + int(row.issue == 'B'),None) if row else (None,'missing')


def analyze(job):
    from docx import Document
    from jobs.artifacts import materialize_job_input,temporary_output
    from jobs.contracts import JobExecutionResult
    from jobs.execution import update_progress
    from word.analysis_contracts import resolve_analysis_checks
    source = materialize_job_input(job)
    try:
        pars = [p.text.strip() for p in Document(source).paragraphs]
    finally:
        source.unlink(missing_ok=True)
    terms = {'compliance_documents':'belge listesi','abbreviations':'kısaltma','attachments':'ekler','revision_history':'revizyon geçmişi','approvals':'onay'}
    checks = resolve_analysis_checks(job.parameters.get('check_ids'),job.parameters.get('custom_checks'))
    results = []
    for i,check in enumerate(checks,1):
        term = terms.get(check['id'],check['title'].strip('?').casefold())
        index = next((j for j,t in enumerate(pars) if term in t.casefold()),None)
        found = index is not None
        text = pars[min(index+1,len(pars)-1)] if found else ''
        evidence = [{'text':text,'score':1.0,'source_type':'paragraph','heading':pars[index],'paragraph_index':min(index+1,len(pars)-1),'table_index':None,'row_index':None}] if found else []
        results.append({**check,'score':float(found),'status':'success' if found else 'error','explanation':('Örnek belgede ilgili bölüm başlığı ve kaynak paragrafı eşleşti.' if found else 'Örnek belgede ilgili başlık bulunamadı.'),'evidence':evidence})
        update_progress(job.id,10+int(78*i/len(checks)),f'Belge kontrolü {i}/{len(checks)}')
        time.sleep(.35)
    passed = sum(r['status']=='success' for r in results)
    summary = {'type':'document_analysis','overall_score':round(passed/len(results),6),'passed':passed,'total':len(results),'checks':[{k:r[k] for k in ('id','title','status','score')} for r in results]}
    out = temporary_output('.json')
    out.write_text(json.dumps({'document':job.input_name,'checks':results},ensure_ascii=False),encoding='utf-8')
    return JobExecutionResult(out,'atlas-analiz.json','Belge kontrolü tamamlandı.',summary)


def slides(source,directory):
    from examples import slide_image
    with ZipFile(source) as zipfile:
        images = []
        paths = sorted((name for name in zipfile.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',name)),key=lambda name:int(re.search(r'(\d+)\.xml',name).group(1)))
        for i,name in enumerate(paths,1):
            lines = [e.text for e in ET.fromstring(zipfile.read(name)).iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t') if e.text]
            output = directory/f'slide-{i}.png'
            slide_image(lines[:5]).save(output)
            images.append(output)
        return images


def assistant(messages, **kwargs):
    context = json.loads(messages[0].content.split('Guide data follows:\n',1)[1])
    q = messages[-1].content.casefold()
    guides = context['guides']
    if not guides:
        return json.dumps({'answer':'Bu kullanıcı için erişilebilir bir kılavuz bulunamadı.','application_ids':[],'source_ids':[]})
    rank = lambda g: sum(word.casefold() in q for word in g['keywords']) + int(g['id']==context['current_guide_id'])
    guide = max(guides,key=rank)
    if any(k in q for k in ['iş','görev','job','ilerleme']):
        guide = next((g for g in guides if g['path']=='/jobs'),guide)
    answer = ('İş Merkezi’nde işlemi listeden seçin. Durumunu ve ilerleme adımlarını ayrıntı panelinde izleyin. Başarılı işlemin dosyasını aynı panelden indirin.' if 'job' in guide['id'].lower() else f"{guide['title']} kılavuzuna aşağıdaki bağlantıdan ulaşabilirsiniz.")
    return json.dumps({'answer':answer,'application_ids':[guide['id']],'source_ids':[guide['id']]},ensure_ascii=False)


def doors_status():
    from jobs.models import WorkerHeartbeat
    from django.utils import timezone
    from datetime import timedelta
    active = WorkerHeartbeat.objects.filter(worker_id='doors-worker:atlas-demo',heartbeat_at__gte=timezone.now()-timedelta(seconds=30)).count()
    return {'configured':True,'available':bool(active),'active_workers':active,'platform_supported':True,'transport':'windows-worker'}


def install():
    if os.environ.get('AW_VIDEO_DEMO') != '1' or not os.environ.get('AW_DEMO_GENERATION') or not settings.DEBUG:
        raise RuntimeError('The isolated recording profile is required.')
    from integrations import catalog, docproof_views
    from integrations.assistant import service as chat, views as chat_views
    from integrations.doors import api_views as door_views, services as door_services, worker_tasks
    from integrations.teamcenter import views as tc_views, job_executor as tc_jobs
    from compliance import services as compliance
    from ddf import views as ddf
    from pptxgallery import job_executor as pptx
    door_services.integration_status = door_views.integration_status = doors_status
    worker_tasks.execute_with_client = lambda action: action(Doors())
    tc_jobs.execute_with_client = tc_views.execute_with_client = lambda action: action(Teamcenter())
    tc_views.integration_status = catalog.teamcenter_status = lambda: {'configured':True,'auth_mode':'password','service_root':'RestServices','tls_verification_enabled':True}
    compliance.search_document_issue = docproof_views.search_document_issue = docproof
    chat.complete_text = assistant
    chat_views.configuration_status = catalog.configuration_status = lambda: 'configured'
    ddf.request_assessment = lambda prompt: ', '.join('Editöryel Görüş' if 'tarih' in line.casefold() else 'Teknik Görüş' for line in ast.literal_eval(prompt.split('\n',1)[1]))
    pptx.render_pptx_to_images = slides


def resolve(kind):
    return analyze if kind == 'word.analyze' else None
