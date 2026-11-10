"""Restore only this scene's named fictional objects before a repeat take."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend_demo"))
from run import prepare

def main(scene):
    generation = prepare(False)
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from compliance.models import ComplianceDocument, CoverPage, CoverPageNumberAllocation, DocumentStatus, ReviewTask
    from integrations.jira.user_content_models import JiraUserContent
    from integrations.jira.workflow_models import JiraTrackedIssue
    from orgs.models import Project
    from word.models import DocumentAnalysisUserContent

    if Path(settings.DATABASES["default"]["NAME"]).resolve() != generation / "demo.sqlite3":
        raise RuntimeError("A recording scene may only reset its isolated generation.")
    owner = get_user_model().objects.get(username="D10001")
    project = Project.objects.get(slug="gokbey", name="Atlas Demo Projesi")
    with transaction.atomic():
        if scene in ("compliance-register","compliance-import"):
            refs = ["ATL-KPK-900"] if scene == "compliance-register" else ["ATL-KP-098","ATL-KP-099"]
            covers = CoverPage.objects.filter(project=project, number__in=refs)
            ComplianceDocument.objects.filter(project=project,cover_page__in=covers).delete()
            covers.delete()
        elif scene == "compliance-numbering":
            names = ["Numara bekleyen belge kaydı", "Numara bekleyen teslim listesi",
                     "Atlas teslim numarası örneği"]
            previous = ComplianceDocument.objects.filter(project=project,name__in=names)
            cover_ids = list(previous.values_list("cover_page_id",flat=True))
            CoverPageNumberAllocation.objects.filter(project=project,document__in=previous).delete()
            previous.delete()
            for cover in CoverPage.objects.filter(project=project,pk__in=cover_ids):
                if not ComplianceDocument.objects.filter(cover_page=cover).exists():
                    cover.delete()
            for index,name in enumerate(names[:2]):
                blank=CoverPage.objects.create(project=project,number="",issue="A")
                ComplianceDocument.objects.create(project=project,cover_page=blank,name=name,
                    number=f"ATL-SIRA-{index+1:02}",owner=owner)
        elif scene == "compliance-archive":
            from compliance.services import set_archive_state
            doc=ComplianceDocument.objects.get(project=project,number="ATL-DOK-017")
            if doc.is_archived:
                set_archive_state(project=project,document_id=doc.id,expected_version=doc.version,
                                  archived=False,reason="Demo başlangıç durumu.",user=owner)
        elif scene == "compliance-decisions":
            from compliance.services import request_review
            doc=ComplianceDocument.objects.get(project=project,number="ATL-DOK-019")
            for kind,note in [("review","Teslim listesinin sürümünü incele."),
                              ("approval","Dizin taslağını onayla.")]:
                ReviewTask.objects.filter(document=doc,request_note=note).delete()
                request_review(project=project,document_id=doc.id,expected_version=doc.version,
                    kind=kind,assignee=owner,due_date=None,request_note=note,user=owner)
        elif scene == "compliance-workflow":
            ReviewTask.objects.filter(document__project=project,
                document__number="ATL-DOK-011",request_note="Dizin ve sürüm eşleşmesini doğrula.").delete()
        elif scene == "compliance-settings":
            DocumentStatus.objects.filter(project=project,label="Yayın sırası").delete()
        elif scene == "jira-watcher":
            JiraTrackedIssue.objects.filter(projects=project, owner=owner, issue="DEMO-102").delete()
        elif scene in ("jira-subtasks", "jira-lists"):
            JiraUserContent.objects.filter(user=owner).delete()
        elif scene == "document-analysis":
            DocumentAnalysisUserContent.objects.filter(user=owner).delete()
        else:
            raise ValueError("Unknown scene fixture.")

if __name__ == "__main__":
    if os.environ.get("AW_VIDEO_DEMO") != "1":
        raise SystemExit("AW_VIDEO_DEMO=1 is required")
    main(sys.argv[1])
