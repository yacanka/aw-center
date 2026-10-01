"""Inspection and comparison for a selected pair of single-sheet tables."""

from openpyxl.utils import get_column_letter

from .contracts import CompareError, ComparisonResult, Difference, TextBlock
from .excel_reading import read_tables, column_pairs, display
from .excel_matching import match_rows, cell_score, cell_identity
from .matching import difference


def prepare(old_content, new_content, selection, options, checkpoint):
    if not isinstance(selection, dict):
        raise CompareError('Select valid table options.')
    old, first = read_tables(old_content, selection.get('first', {}), checkpoint)
    new, second = read_tables(new_content, selection.get('second', {}), checkpoint)
    mappings = column_pairs(old, new, selection.get('columns'))
    pairs, matching = match_rows(old, new, mappings, selection.get('matching', {}), options, checkpoint)
    if first['header_confirmation_required'] or second['header_confirmation_required']:
        matching = {**matching, 'requires_input': True,
                    'reason': 'The suggested header excludes populated rows. Check both header rows, then inspect again to confirm.'}
    resolved = {'first': first['selected'], 'second': second['selected'], 'columns': mappings,
                'matching': {'mode': matching['method'] if matching['method'] != 'content' else 'auto',
                             'keys': matching['keys']}}
    inspection = {'first': first, 'second': second, 'selection': resolved, 'matching': matching,
                  'warnings': ['Only the selected table on each worksheet is compared. Formulas are not evaluated.']}
    for label, details in (('Old', first), ('New', second)):
        if details['excluded_rows']:
            inspection['warnings'].append(f"{label} table: {details['excluded_rows']} populated rows before the selected header are excluded.")
    return old, new, mappings, pairs, inspection


def inspect_excel(old_content, new_content, selection, options, checkpoint=lambda: None):
    return prepare(old_content, new_content, selection, options, checkpoint)[4]


def block(table, row_number, column, value):
    return TextBlock(display(value), f'{table.sheet}!{get_column_letter(column + 1)}{row_number}')


def schema_differences(old, new, mappings, options):
    output = []
    for left, right in mappings:
        output.append(difference(block(old, old.header_row, left, old.columns[left]),
                                 block(new, new.header_row, right, new.columns[right]), options,
                                 cell_score(old.columns[left], new.columns[right]), 'Column header'))
    for index, label in enumerate(old.columns):
        if index not in {pair[0] for pair in mappings}:
            output.append(difference(block(old, old.header_row, index, label), None, options, field='Column header'))
    for index, label in enumerate(new.columns):
        if index not in {pair[1] for pair in mappings}:
            output.append(difference(None, block(new, new.header_row, index, label), options, field='Column header'))
    return output


def paired_cells(old, new, first, second, mappings, options):
    first_number, old_values = first
    second_number, new_values = second
    output = []
    for left, right in mappings:
        old_block = block(old, first_number, left, old_values[left])
        new_block = block(new, second_number, right, new_values[right])
        entry = difference(old_block, new_block, options, cell_score(old_values[left], new_values[right]), old.columns[left])
        if entry.change == 'equal' and cell_identity(old_values[left]) != cell_identity(new_values[right]):
            entry = Difference('replace', old_block.text, new_block.text, old_block.location,
                               new_block.location, 'none', 0.0, f'{old.columns[left]} (cell type changed)')
        output.append(entry)
    output.extend(difference(block(old, first_number, index, value), None, options, field=old.columns[index])
                  for index, value in enumerate(old_values) if index not in {pair[0] for pair in mappings})
    output.extend(difference(None, block(new, second_number, index, value), options, field=new.columns[index])
                  for index, value in enumerate(new_values) if index not in {pair[1] for pair in mappings})
    return output


def compare_excel(old_content, new_content, selection, options, checkpoint=lambda: None):
    old, new, mappings, pairs, inspection = prepare(old_content, new_content, selection, options, checkpoint)
    if inspection['matching']['requires_input']:
        raise CompareError(inspection['matching']['reason'], 'COMPARE_MATCHING_REQUIRED')
    output = schema_differences(old, new, mappings, options)
    used = set()
    for index, row in enumerate(old.rows):
        if index % 100 == 0:
            checkpoint()
        if index in pairs:
            target, _score = pairs[index]
            used.add(target)
            output.extend(paired_cells(old, new, row, new.rows[target], mappings, options))
        else:
            output.extend(difference(block(old, row[0], col, value), None, options, field=old.columns[col])
                          for col, value in enumerate(row[1]))
    for index, row in enumerate(new.rows):
        if index not in used:
            output.extend(difference(None, block(new, row[0], col, value), options, field=new.columns[col])
                          for col, value in enumerate(row[1]))
    return ComparisonResult('excel', options, output, inspection['matching']['method'], inspection['warnings'])
