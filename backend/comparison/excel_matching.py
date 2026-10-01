"""Conservative table identity inference and bounded mutual-best matching."""

from collections import defaultdict, deque
from itertools import combinations
from numbers import Number
from datetime import date, time

from .contracts import CompareError, MAX_CANDIDATES, check_limit
from .excel_reading import display
from .matching import normalize, similarity


def cell_identity(value):
    # Keep text identifiers such as 001 distinct from the number 1.
    kind = 'number' if isinstance(value, Number) and not isinstance(value, bool) else type(value).__name__
    return kind, display(value)


def row_key(row, columns):
    return tuple(cell_identity(row[index]) for index in columns)


def unique_keys(table, columns):
    keys = [row_key(row, columns) for _, row in table.rows]
    complete = all(all(display(row[index]).strip() for index in columns) for _, row in table.rows)
    return keys, complete and len(set(keys)) == len(keys)


def key_pairs(old, new, mappings, keys):
    lookup = dict(mappings)
    if (not isinstance(keys, list) or not 1 <= len(keys) <= 3
            or any(type(key) is not int or key not in lookup for key in keys) or len(set(keys)) != len(keys)):
        raise CompareError('Select one to three mapped identity columns.')
    old_keys, old_unique = unique_keys(old, keys)
    new_keys, new_unique = unique_keys(new, [lookup[key] for key in keys])
    if not old_unique or not new_unique:
        raise CompareError('Identity columns must be non-empty and unique in both tables.', 'COMPARE_DUPLICATE_KEYS')
    return old_keys, new_keys


def suggest_keys(old, new, mappings, checkpoint):
    # A fixed search budget bounds combinations on wide spreadsheets.
    attempts = 0
    for width in range(1, 4):
        for columns in combinations([pair[0] for pair in mappings], width):
            attempts += 1
            if attempts > 500:
                return None
            if attempts % 25 == 0:
                checkpoint()
            try:
                left, right = key_pairs(old, new, mappings, list(columns))
            except CompareError:
                continue
            overlap = len(set(left) & set(right)) / max(len(left), len(right), 1)
            if overlap >= .8:
                return list(columns)
    return None


def cell_score(first, second):
    if cell_identity(first) == cell_identity(second):
        return 1.0
    if isinstance(first, (Number, date, time)) or isinstance(second, (Number, date, time)):
        return 0.0
    return similarity(normalize(display(first)), normalize(display(second)))


def row_score(first, second, mappings):
    values = [cell_score(first[left], second[right]) for left, right in mappings
              if display(first[left]) or display(second[right])]
    return sum(values) / len(values) if values else 0.0


def content_pairs(old, new, mappings, options, checkpoint):
    destinations = defaultdict(deque)
    for index, (_, row) in enumerate(new.rows):
        destinations[row_key(row, [pair[1] for pair in mappings])].append(index)
    pairs, used = {}, set()
    for index, (_, row) in enumerate(old.rows):
        candidates = destinations[row_key(row, [pair[0] for pair in mappings])]
        if candidates:
            target = candidates.popleft()
            pairs[index] = (target, 1.0)
            used.add(target)
    left = [index for index in range(len(old.rows)) if index not in pairs]
    right = [index for index in range(len(new.rows)) if index not in used]
    check_limit(len(left) * len(right) > MAX_CANDIDATES,
                'Too many candidate rows. Select identity columns or row-order matching.')
    by_left, by_right = defaultdict(list), defaultdict(list)
    for offset, source in enumerate(left):
        if offset % 20 == 0:
            checkpoint()
        for target in right:
            score = row_score(old.rows[source][1], new.rows[target][1], mappings)
            by_left[source].append((score, target))
            by_right[target].append((score, source))
    for values in (*by_left.values(), *by_right.values()):
        values.sort(reverse=True)
    ambiguous = 0
    for source in left:
        candidates = by_left[source]
        if not candidates:
            continue
        score, target = candidates[0]
        reverse = by_right[target]
        margin = score - (candidates[1][0] if len(candidates) > 1 else 0)
        reverse_margin = score - (reverse[1][0] if len(reverse) > 1 else 0)
        if score >= options.equal_ratio and reverse[0][1] == source and min(margin, reverse_margin) >= .10:
            pairs[source] = (target, score)
        elif score >= options.weak_equal_ratio:
            ambiguous += 1
    # With changed rows on both sides, absence of a reliable match is itself
    # uncertainty, not proof that every row was deleted and recreated.
    if left and right and not any(index in pairs for index in left):
        ambiguous = max(ambiguous, len(left))
    return pairs, ambiguous


def match_rows(old, new, mappings, selected, options, checkpoint=lambda: None):
    if not isinstance(selected, dict):
        raise CompareError('Select a row matching method.')
    mode = selected.get('mode', 'auto')
    if mode not in ('auto', 'keys', 'position'):
        raise CompareError('Select a supported row matching method.')
    if mode == 'position':
        return {i: (i, 1.0) for i in range(min(len(old.rows), len(new.rows)))}, {
            'method': 'position', 'requires_input': False, 'reason': 'Rows paired by their selected table order.', 'keys': []}
    if not mappings:
        return {}, {'method': 'content', 'requires_input': True,
                    'reason': 'Map corresponding columns, or explicitly select row-order matching.', 'keys': []}
    keys = selected.get('keys') if mode == 'keys' else suggest_keys(old, new, mappings, checkpoint)
    if keys:
        left, right = key_pairs(old, new, mappings, keys)
        lookup = {key: index for index, key in enumerate(right)}
        pairs = {index: (lookup[key], 1.0) for index, key in enumerate(left) if key in lookup}
        return pairs, {'method': 'keys', 'requires_input': False, 'reason': 'Non-empty, unique identity columns.', 'keys': keys}
    if mode == 'keys':
        raise CompareError('Select at least one identity column.')
    try:
        pairs, ambiguous = content_pairs(old, new, mappings, options, checkpoint)
    except CompareError as error:
        if error.code != 'COMPARE_LIMIT_EXCEEDED':
            raise
        return {}, {'method': 'content', 'requires_input': True, 'keys': [],
                    'reason': 'Content matching exceeds safe limits. Select identity columns or row-order matching.'}
    return pairs, {'method': 'content', 'requires_input': ambiguous > 0, 'keys': [],
                   'ambiguous_count': ambiguous,
                   'reason': ('Some rows cannot be matched confidently. Select identity columns or row order.'
                              if ambiguous else 'Exact rows and unambiguous mutual-best content matches.')}
