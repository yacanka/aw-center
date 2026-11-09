"""Restore the named provider fixture before a DOORS demonstration take."""
import sqlite3
import sys
from contextlib import closing
import json

from run import prepare


def main(scene):
    generation = prepare(False)
    if scene=='galeri-bakim':
        from pptxgallery.models import Presentation
        Presentation.objects.filter(owner__username='D10001',title='Atlas yayın özeti').delete()
        return
    path = generation/'providers.sqlite3'
    if not path.exists():
        return
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if scene=='baglama':
            db.execute("DELETE FROM entries WHERE domain='links' AND ident='/Atlas/BelgeBaglari'")
        elif scene=='nesne':
            row = db.execute("SELECT data FROM entries WHERE domain='doors' AND ident='/Atlas/Belgeler'").fetchone()
            if row:
                rows = [r for r in json.loads(row[0]) if r.get('Object Heading')!='Teslim kontrolü']
                db.execute("UPDATE entries SET data=? WHERE domain='doors' AND ident='/Atlas/Belgeler'",(json.dumps(rows,ensure_ascii=False),))
        else:
            raise SystemExit('Unknown engineering fixture.')


if __name__ == '__main__':
    main(sys.argv[1])
