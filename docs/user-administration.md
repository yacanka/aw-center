# Users administration

The Users route and navigation entry require an active staff account with
`auth.view_user` or `auth.add_user`. Active superusers have full access.
The API independently checks staff status and the permission for each operation.
Possessing a user permission alone never exposes administration to ordinary users.

| Operation | Delegated administrator | Superuser |
| --- | --- | --- |
| List users and permission catalog | `auth.view_user` | Yes |
| View shared roles | `auth.view_group` | Yes |
| Edit ordinary profiles | `auth.change_user` | Yes |
| Delete ordinary accounts | `auth.delete_user` | Yes |
| Create invitations without initial roles | `auth.add_user` | Yes |
| Assign roles or direct permissions, including invitation roles | No | Yes |
| Create, edit or delete shared roles | No | Yes |
| Change active/staff status or edit administrators | No | Yes |

Account and role permissions remain Django permissions; no parallel role store is
introduced. Project membership and record-level access checks still apply. Role
edits affect every member; removing a direct permission does not remove the same
permission inherited from a role. Superuser status cannot be granted through this
API. Users cannot delete themselves, delete a superuser, or disable their own
administrator access or a superuser account.

This tightens the previous API contract: non-staff users with model permissions
can no longer administer users, and delegated administrators must ask a superuser
for access assignments. Existing groups and user permissions are preserved.

The directory uses server-side search and account filters before pagination.
User drafts are isolated until saving; failed requests keep the editor open.
The desktop directory and mobile cards expose the same permitted operations.
Role tooltips are available with a pointer, keyboard focus and touch.
