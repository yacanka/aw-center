"""Reserve email identities without modifying any existing account data."""
from django.db import migrations, models


SQLITE_TRIGGERS = (
    # REPLACE may delete a conflicting row without running DELETE triggers.
    # Reject key collisions explicitly, including conflict-ignoring inserts.
    """CREATE TRIGGER users_email_identity_insert_key BEFORE INSERT ON auth_user BEGIN
         SELECT RAISE(ABORT, 'users_account_key_conflict') WHERE EXISTS (
           SELECT 1 FROM auth_user WHERE id = NEW.id OR username = NEW.username
         );
       END""",
    """CREATE TRIGGER users_email_identity_update_key BEFORE UPDATE OF id, username ON auth_user BEGIN
         SELECT RAISE(ABORT, 'users_account_key_conflict') WHERE EXISTS (
           SELECT 1 FROM auth_user
           WHERE (id = NEW.id OR username = NEW.username) AND id <> OLD.id
         );
       END""",
    """CREATE TRIGGER users_email_identity_insert AFTER INSERT ON auth_user
       WHEN lower(trim(NEW.email)) <> '' BEGIN
         SELECT RAISE(ABORT, 'users_email_identity_conflict')
         WHERE EXISTS (SELECT 1 FROM users_email_identity WHERE email = lower(trim(NEW.email)));
         INSERT INTO users_email_identity(email, owner_count)
         VALUES (lower(trim(NEW.email)), 1);
       END""",
    """CREATE TRIGGER users_email_identity_update AFTER UPDATE OF email ON auth_user
       WHEN lower(trim(NEW.email)) <> lower(trim(OLD.email)) BEGIN
         SELECT RAISE(ABORT, 'users_email_identity_conflict')
         WHERE EXISTS (SELECT 1 FROM users_email_identity WHERE email = lower(trim(NEW.email)));
         INSERT INTO users_email_identity(email, owner_count)
         SELECT lower(trim(NEW.email)), 1 WHERE lower(trim(NEW.email)) <> '';
         UPDATE users_email_identity SET owner_count = owner_count - 1
         WHERE email = lower(trim(OLD.email));
         DELETE FROM users_email_identity WHERE email = lower(trim(OLD.email)) AND owner_count = 0;
       END""",
    """CREATE TRIGGER users_email_identity_delete AFTER DELETE ON auth_user BEGIN
         UPDATE users_email_identity SET owner_count = owner_count - 1
         WHERE email = lower(trim(OLD.email));
         DELETE FROM users_email_identity WHERE email = lower(trim(OLD.email)) AND owner_count = 0;
       END""",
)

POSTGRES_FUNCTION = """
CREATE FUNCTION users_email_identity_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF lower(trim(NEW.email)) = lower(trim(OLD.email)) THEN
      RETURN NEW;
    END IF;
  END IF;
  IF TG_OP <> 'DELETE' THEN
    IF lower(trim(NEW.email)) <> '' THEN
      INSERT INTO users_email_identity(email, owner_count)
      VALUES (lower(trim(NEW.email)), 1);
    END IF;
  END IF;
  IF TG_OP <> 'INSERT' THEN
    UPDATE users_email_identity SET owner_count = owner_count - 1
    WHERE email = lower(trim(OLD.email));
    DELETE FROM users_email_identity
    WHERE email = lower(trim(OLD.email)) AND owner_count = 0;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


def install_guard(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in {'sqlite', 'postgresql'}:
        raise RuntimeError('Email identity guard requires SQLite or PostgreSQL.')
    if vendor == 'postgresql':
        # Exclude writers between the backfill and trigger installation.
        schema_editor.execute('LOCK TABLE auth_user IN SHARE ROW EXCLUSIVE MODE')
    schema_editor.execute("""
        INSERT INTO users_email_identity(email, owner_count)
        SELECT lower(trim(email)), count(*) FROM auth_user
        WHERE trim(email) <> '' GROUP BY lower(trim(email))
    """)
    if vendor == 'sqlite':
        for sql in SQLITE_TRIGGERS:
            schema_editor.execute(sql)
    else:
        schema_editor.execute(POSTGRES_FUNCTION)
        schema_editor.execute("""
            CREATE TRIGGER users_email_identity_write
            AFTER INSERT OR UPDATE OF email OR DELETE ON auth_user
            FOR EACH ROW EXECUTE FUNCTION users_email_identity_guard()
        """)


def uninstall_guard(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        for suffix in ('insert', 'update', 'delete', 'insert_key', 'update_key'):
            schema_editor.execute(f'DROP TRIGGER users_email_identity_{suffix}')
    elif schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP TRIGGER users_email_identity_write ON auth_user')
        schema_editor.execute('DROP FUNCTION users_email_identity_guard()')


class Migration(migrations.Migration):
    dependencies = [('users', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='EmailIdentity',
            fields=[
                ('email', models.CharField(max_length=254, primary_key=True, serialize=False)),
                ('owner_count', models.PositiveIntegerField()),
            ],
            options={'db_table': 'users_email_identity'},
        ),
        migrations.RunPython(install_guard, uninstall_guard),
    ]
