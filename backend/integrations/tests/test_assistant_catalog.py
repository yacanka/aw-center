"""Permission and bounded-context contracts for the application guide."""
import json
from dataclasses import asdict, replace
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission, AnonymousUser
from django.test import TestCase, SimpleTestCase
from integrations.assistant.catalog import load_guides
from integrations.assistant.access import authorized_guides
from integrations.assistant.context import build_context
from orgs.models import Project, ProjectRoleAssignment


class AssistantAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="guide-user")
        Project.objects.all().update(enabled=False)
        self.project = Project.objects.get(slug="aesa")
        self.project.enabled = True
        self.project.save()

    def paths(self, user=None):
        return {entry.path for entry in authorized_guides(user or self.user)}

    def grant(self, domain, *, group=None, project=None):
        return ProjectRoleAssignment.objects.create(
            project=project or self.project, domain=domain, role="viewer",
            **({"group": group} if group else {"user": self.user}),
        )

    def test_catalog_matches_effective_menu_access(self):
        paths = self.paths()
        self.assertIn("/compare", paths)
        self.assertNotIn("/users", paths)
        self.assertNotIn("/developer/doors", paths)
        self.assertNotIn("/developer/test-data", paths)
        self.assertNotIn("/ddfAssistant", paths)
        self.user.is_staff = True
        self.user.save()
        self.assertIn("/developer/doors", self.paths())
        self.assertNotIn("/users", self.paths())
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="auth", codename="view_user"))
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.assertIn("/users", self.paths())
        group = Group.objects.create(name="ddf readers")
        group.permissions.add(Permission.objects.get(content_type__app_label="ddf", codename="view_ddf"))
        self.user.groups.add(group)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.assertIn("/ddfAssistant", self.paths())
        self.user.is_superuser = True
        self.user.save()
        self.assertIn("/developer/test-data", self.paths())
        self.assertEqual(authorized_guides(AnonymousUser()), ())
        self.user.is_active = False
        self.assertEqual(authorized_guides(self.user), ())

    def test_project_guides_require_enabled_capability_and_domain_role(self):
        self.grant("dcc")
        self.assertIn("/jira", self.paths())
        self.assertNotIn("/compdocs/aesa", self.paths())
        self.assertNotIn("/organization", self.paths())
        group = Group.objects.create(name="compliance readers")
        self.user.groups.add(group)
        self.grant("compliance", group=group)
        self.assertIn("/compdocs/aesa", self.paths())
        self.assertIn("/compdocs/docAnalyzer", self.paths())
        self.grant("organization")
        self.assertIn("/organization", self.paths())
        wrong = Project.objects.get(slug="hurkus")
        wrong.enabled = True
        wrong.save()
        self.grant("compliance", project=wrong)
        self.assertNotIn("/compdocs/hurkus", self.paths())
        self.project.enabled = False
        self.project.save()
        self.assertNotIn("/compdocs/aesa", self.paths())
        self.assertNotIn("/jira", self.paths())

    def test_context_refilters_after_role_revocation(self):
        assignment = self.grant("compliance")
        before = authorized_guides(self.user)
        self.assertIn("/compdocs/aesa", build_context(before, current_path="/compdocs/aesa", message="help"))
        assignment.delete()
        after = authorized_guides(self.user)
        context = build_context(after, current_path="/compdocs/aesa", message="aesa")
        self.assertNotIn("/compdocs/aesa", context)


class GuideContextTests(SimpleTestCase):
    def test_current_page_is_identified_explicitly_in_context(self):
        context = json.loads(build_context(load_guides(), current_path="/accelerator", message="What can I do on this page?"))
        self.assertEqual(context.get("current_guide_id", "missing"), "accelerator")
        self.assertIn("accelerator", {row["id"] for row in context["guides"]})

    def test_unknown_empty_or_unauthorized_current_page_has_no_guide_id(self):
        guides = tuple(entry for entry in load_guides() if entry.id != "users")
        for current_path in ("/unknown-private-page", "", "/users"):
            with self.subTest(current_path=current_path):
                context = build_context(guides, current_path=current_path, message="What can I do on this page?")
                self.assertIsNone(json.loads(context).get("current_guide_id", "missing"))
                if current_path:
                    self.assertNotIn(current_path, context)

    def test_raw_url_state_does_not_identify_a_current_guide(self):
        for current_path in ("/accelerator?private=PRIVATE", "/accelerator#FRAGMENT",
                             "https://private.example/accelerator?private=PRIVATE#FRAGMENT"):
            with self.subTest(current_path=current_path):
                context = build_context(load_guides(), current_path=current_path, message="Help")
                self.assertIsNone(json.loads(context).get("current_guide_id", "missing"))
                self.assertNotIn("PRIVATE", context)
                self.assertNotIn("FRAGMENT", context)
                self.assertNotIn("private.example", context)

    def test_budget_omitted_current_guide_has_no_guide_id(self):
        base = load_guides()[0]
        oversized = replace(base, id="oversized", path="/oversized", purpose="ğ" * 40000)
        context = build_context((base, oversized), current_path="/oversized", message="Help")
        data = json.loads(context)
        self.assertIsNone(data.get("current_guide_id", "missing"))
        self.assertNotIn("oversized", {row["id"] for row in data["guides"]})
        self.assertIn(base.id, {row["id"] for row in data["guides"]})
        self.assertLessEqual(len(context.encode("utf-8")), 64 * 1024)

    def test_current_guide_id_is_counted_in_the_context_byte_budget(self):
        from integrations.assistant.context import GENERAL_HELP
        base = replace(load_guides()[0], id="near-limit", path="/near-limit", purpose="")
        envelope = {"general_help": GENERAL_HELP, "current_guide_id": "near-limit", "guides": [asdict(base)]}
        overhead = len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        near_limit = replace(base, purpose="x" * (64 * 1024 - overhead + 1))
        context = build_context((near_limit,), current_path="/near-limit", message="Help")
        data = json.loads(context)
        self.assertEqual(len(data["guides"]), 0)
        self.assertIsNone(data.get("current_guide_id", "missing"))
        self.assertLessEqual(len(context.encode("utf-8")), 64 * 1024)

    def test_catalog_validates_duplicate_ids(self):
        import json
        import tempfile
        from pathlib import Path
        from dataclasses import asdict
        row = asdict(load_guides()[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guides.json"
            path.write_text(json.dumps([row, row]), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_guides(path)

    def test_context_is_deterministic_utf8_bounded_and_prioritizes_current_page(self):
        base = load_guides()[0]
        huge = tuple(replace(base, id=f"tool-{index:03}", path=f"/tool-{index}", purpose="ğ" * 15000)
                     for index in range(10))
        context = build_context(huge, current_path="/tool-9", message="")
        self.assertLessEqual(len(context.encode("utf-8")), 64 * 1024)
        self.assertIn("/tool-9", context)
        self.assertEqual(context, build_context(tuple(reversed(huge)), current_path="/tool-9", message=""))

    def test_project_details_require_explicit_authorized_selection(self):
        base = load_guides()[0]
        aesa = replace(base, id="compliance-project-aesa", title="AESA",
                       path="/compdocs/aesa", keywords=("aesa", "AESA", "compliance"))
        piku = replace(base, id="compliance-project-piku", title="Piku",
                       path="/compdocs/piku", keywords=("piku", "Piku", "compliance"))
        guides = (base, aesa, piku)
        general = build_context(guides, current_path="/home", message="compliance")
        self.assertNotIn("/compdocs/aesa", general)
        self.assertNotIn("/compdocs/piku", general)
        selected = build_context(guides, current_path="/home", message="Help with AESA")
        self.assertIn("/compdocs/aesa", selected)
        self.assertNotIn("/compdocs/piku", selected)
        self.assertNotIn("/compdocs/aesa", build_context(guides, current_path="/compdocs/aesa?secret=x", message=""))
        self.assertNotIn("/compdocs/aesa", build_context(guides, current_path="/home", message="xaesax"))
