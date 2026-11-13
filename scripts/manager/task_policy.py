"""Fixed desktop action resource rules; no filesystem or network I/O on Tk."""
from __future__ import annotations

from dataclasses import dataclass
import os


ACTION_LABELS = {'ensure': 'AW Center’ı aç', 'provision': 'Kur ve başlat', 'start': 'Başlat', 'doctor': 'Tam doğrula',
                 'test-sources': 'Kaynak testi', 'bundle': 'Offline paket hazırla', 'inspect': 'Ortam denetimi'}


@dataclass(frozen=True)
class Claim:
    resource: str
    write: bool = False
    path: bool = False


def _path(value):
    # Resolving symlinks/UNC paths can block. Workers independently reject linked
    # installation paths; UI admission only needs lexical collision detection.
    return os.path.normcase(os.path.abspath(os.path.normpath(str(value))))


def claims_for(action: str, values: dict) -> tuple[Claim, ...]:
    """Reserve real mutations and per-profile lifecycle, never a global UI lock."""
    profile = values.get('profile', 'dev')
    if action == 'ensure':
        # Worker acquires authoritative branch-specific OS leases after its
        # read-only decision. A blanket runtime write claim would block starting
        # a prepared prod while dev is already running.
        return (Claim(f'lifecycle:{profile}', write=True),)
    if action in {'doctor', 'test-sources', 'inspect'}:
        return (Claim(f'{action}:{profile}', write=True),)
    claims = [Claim('managed-runtime', write=action == 'provision')]
    if action in {'provision', 'start'}:
        # Production releases share one DB/state even when source paths differ.
        claims.append(Claim(f'lifecycle:{profile}', write=True))
    source = values.get('source_root')
    if source:
        claims.append(Claim(_path(source), write=action == 'provision', path=True))
    if action == 'bundle' and values.get('output'):
        claims.append(Claim(_path(values['output']), write=True, path=True))
    return tuple(claims)


def conflicts(left: tuple[Claim, ...], right: tuple[Claim, ...]) -> bool:
    for first in left:
        for second in right:
            if first.path != second.path or not (first.write or second.write):
                continue
            if not first.path and first.resource == second.resource:
                return True
            if first.path:
                try:
                    shared = os.path.commonpath((first.resource, second.resource))
                except ValueError:  # Different Windows drives cannot overlap.
                    continue
                if shared in {first.resource, second.resource}:
                    return True
    return False
