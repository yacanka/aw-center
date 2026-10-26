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

Django admin user/group creation, changes, deletion and user password changes
require an active superuser. Existing view permissions remain available for
read-only pages and project-role subject autocomplete. Delegated profile editing
continues through the Users API.

Browser password forms accept at most 128 characters and preserve leading and
trailing whitespace. Login, invitation, reset, profile password change and
administrator password forms use the same boundary.

The directory uses server-side search and account filters before pagination.
User drafts are isolated until saving; failed requests keep the editor open.
The desktop directory and mobile cards expose the same permitted operations.
Role tooltips are available with a pointer, keyboard focus and touch.

Account email identities are reserved by database triggers using `lower(trim(email))`.
New nonblank identities cannot collide, including concurrent API, invitation, admin,
and bulk ORM writes. Blank emails remain allowed. SQLite LOWER folds ASCII only;
PostgreSQL LOWER follows the database collation. Validation and password-recovery
lookup use the same database expression, rather than Python Unicode casefold.

The forward `users.0002_email_identity_guard` migration counts existing owners in
`users_email_identity`; it does not change or delete accounts or their email values.
Existing duplicate identities can keep their address and edit unrelated fields,
but cannot acquire another owner. Recovery for an ambiguous identity remains neutral
and sends nothing. Moving/deleting one legacy owner keeps the identity reserved
until its last owner leaves. The reservation table is internal and must not be
edited independently of account writes. A racing admin save rolls back and returns
to the form with an email-unavailable message; its unsaved form changes must be
entered again.

SQLite also rejects inserts that reuse an existing account ID/username and
updates that collide with another account's ID/username. This prevents SQLite
`REPLACE` from silently deleting an account without maintaining its reservation.
The narrow compatibility cost is that bulk `ignore_conflicts` cannot silently
ignore an existing account key; callers must handle that integrity conflict.
Ordinary account updates and case-only email edits continue to work.
