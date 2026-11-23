"""Reserve only database and writable artifact locations across desktop profiles."""
import json
from pathlib import Path
from urllib.parse import quote, unquote_plus

from scripts.launcher import installation_profiles as profiles
from scripts.launcher.installation_permissions import require_private
from scripts.launcher.installation_state import installation_lock, private_directory
from scripts.launcher.model import LauncherError


def sqlite_path(backend, url):
    if not url.startswith('sqlite:///') or url == 'sqlite:///:memory:' or '?' in url or '#' in url:
        raise LauncherError('Manager için dosya tabanlı SQLite DATABASE_URL belirtin.')
    name = unquote_plus(url[len('sqlite:///'):])
    if not name or name == ':memory:':
        raise LauncherError('SQLite veritabanı dosya adı eksik.')
    return (backend / Path(name)).resolve()


def sqlite_url(path):
    return 'sqlite:///' + quote(path.as_posix(), safe='/:')


def _read_pair(path):
    if not path.exists():
        return None
    require_private(path)
    pair = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(pair, list) or len(pair) != 2 or
            not all(isinstance(value, str) and Path(value).is_absolute() for value in pair)):
        raise LauncherError('Kayıtlı profil veri yolları okunamadı.')
    return pair


def _same(a, b):
    if a == b:
        return True
    try:
        return a.samefile(b)
    except FileNotFoundError:
        return False


def claim_storage(project, name, database, media):
    """Serialize the comparison and publication, including concurrent first starts."""
    home = profiles.installation_home()
    other = 'prod' if name == 'dev' else 'dev'
    media = (project.backend / media).resolve()
    with installation_lock(home):
        config = private_directory(home / 'config')
        default = home / 'state/production' if other == 'prod' else project.backend
        opposite = [[str(default / 'db.sqlite3'), str(default / 'private_media')]]
        current_other = _read_pair(config / (other + '.storage.json'))
        if current_other:
            opposite.append(current_other)
        legacy = config / (other + '.env')
        if legacy.is_file():
            saved = profiles.read_environment(legacy)
            opposite.append([str(sqlite_path(project.backend, saved['DATABASE_URL'])),
                             str((project.backend / saved['PRIVATE_MEDIA_ROOT']).resolve())])
        for db_name, media_name in opposite:
            db, directory = Path(db_name).resolve(), Path(media_name).resolve()
            if (_same(database, db) or _same(media, directory) or database.is_relative_to(directory)
                    or db.is_relative_to(media) or media.is_relative_to(directory) or directory.is_relative_to(media)):
                raise LauncherError('Local ve Prod için ayrı DATABASE_URL ve PRIVATE_MEDIA_ROOT seçin.')
        path = config / (name + '.storage.json')
        current = [str(database), str(media)]
        if current != _read_pair(path):
            write = profiles._write_replace if path.exists() else profiles._write_new
            write(path, json.dumps(current, ensure_ascii=False))
