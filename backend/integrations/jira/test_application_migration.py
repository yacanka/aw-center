"""Upgrade preserves JIRA records, relations, and permission identities."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class JiraApplicationMigrationTests(TransactionTestCase):
    def test_existing_record_relations_and_permission_ids_survive_adoption(self):
        self.addCleanup(self.restore_latest)
        executor = MigrationExecutor(connection)
        target = [("dcc", "0002_dccreminderdelivery")]
        # Unapply consumers before restoring the old runtime model state.
        executor.migrate([("integrations", None), ("dcc", "0002_dccreminderdelivery"),
                          ("orgs", "0004_seed_dcc_project_variants")])
        old = executor.loader.project_state(target).apps
        User = old.get_model("auth", "User")
        Project = old.get_model("orgs", "Project")
        Record = old.get_model("dcc", "DccRecord")
        ContentType = old.get_model("contenttypes", "ContentType")
        Permission = old.get_model("auth", "Permission")
        ContentType.objects.filter(app_label="integrations", model__in=["jiratrackedissue", "jirareminderdelivery", "jiraissuedraft", "jiraissuedraftevent"]).delete()
        user = User.objects.create(username="migration-owner")
        project, _ = Project.objects.get_or_create(slug="hys", defaults={"name": "HYS"})
        record = Record.objects.create(owner_id=user.pk, issue="HYS-123", title="Saved issue")
        record.projects.add(project)
        record.assigned_users.add(user)
        ct = ContentType.objects.create(app_label="dcc", model="dccrecord")
        permission = Permission.objects.create(content_type=ct, codename="view_dccrecord", name="View")
        user.user_permissions.add(permission)
        assignment = old.get_model("orgs", "ProjectRoleAssignment").objects.create(
            project=project, user=user, domain="dcc", role="operator")
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            new = executor.loader.project_state().apps
            saved = new.get_model("integrations", "JiraTrackedIssue").objects.get(pk=record.pk)
            self.assertEqual(saved.title, "Saved issue")
            self.assertEqual(list(saved.projects.values_list("pk", flat=True)), [project.pk])
            self.assertEqual(list(saved.assigned_users.values_list("pk", flat=True)), [user.pk])
            new_permission = new.get_model("auth", "Permission").objects.get(pk=permission.pk)
            self.assertEqual(new_permission.codename, "view_jiratrackedissue")
            self.assertEqual(new_permission.content_type_id, ct.pk)
            self.assertEqual(list(new_permission.user_set.values_list("pk", flat=True)), [user.pk])
            self.assertEqual(new.get_model("orgs", "ProjectRoleAssignment").objects.get(pk=assignment.pk).domain, "jira")
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def restore_latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
