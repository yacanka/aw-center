"""Bounded text alignment; matching strength never suppresses a real change."""

from collections import defaultdict, deque
from difflib import SequenceMatcher
import re
import unicodedata

from .contracts import Difference, MAX_CANDIDATES, MAX_FUZZY_LENGTH, check_limit


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text).replace('\u200b', '')).strip()


def similarity(first, second):
    if first == second:
        return 1.0
    check_limit(max(len(first), len(second)) > MAX_FUZZY_LENGTH,
                'A changed text block exceeds the matching length limit. Split the input into smaller sections.')
    return SequenceMatcher(None, first, second, autojunk=False).ratio()


def difference(old, new, options, score=None, field=''):
    if old is None:
        return Difference('insert', new=new.text, new_location=new.location, field=field)
    if new is None:
        return Difference('delete', old=old.text, old_location=old.location, field=field)
    if old.text == new.text:
        return Difference('equal', old.text, new.text, old.location, new.location, 'exact', 1.0, field)
    score = similarity(normalize(old.text), normalize(new.text)) if score is None else score
    strength = 'none'
    if score >= options.equal_ratio:
        strength = 'strong'
    elif score >= options.weak_equal_ratio:
        strength = 'possible'
    return Difference('replace', old.text, new.text, old.location, new.location, strength, score, field)


def compare_text(old, new, options, checkpoint=lambda: None):
    """Conserve every block, using exact anchors before bounded fuzzy candidates."""
    destinations = defaultdict(deque)
    for index, block in enumerate(new):
        destinations[normalize(block.text)].append(index)
    pairs = {}
    used = set()
    for index, block in enumerate(old):
        candidates = destinations[normalize(block.text)]
        if candidates:
            target = candidates.popleft()
            pairs[index] = (target, 1.0)
            used.add(target)
    remaining_old = [index for index in range(len(old)) if index not in pairs]
    remaining_new = [index for index in range(len(new)) if index not in used]
    check_limit(len(remaining_old) * len(remaining_new) > MAX_CANDIDATES,
                'Too many changed text blocks to match safely. Compare smaller sections.')
    candidates = []
    for offset, source in enumerate(remaining_old):
        if offset % 20 == 0:
            checkpoint()
        for target in remaining_new:
            score = similarity(normalize(old[source].text), normalize(new[target].text))
            if score >= options.weak_equal_ratio:
                candidates.append((score, source, target))
    for score, source, target in sorted(candidates, key=lambda item: (-item[0], item[1], item[2])):
        if source not in pairs and target not in used:
            pairs[source] = (target, score)
            used.add(target)
    output = []
    for index, block in enumerate(old):
        target, score = pairs.get(index, (None, None))
        output.append(difference(block, new[target] if target is not None else None, options, score))
    output.extend(difference(None, block, options) for index, block in enumerate(new) if index not in used)
    return output
