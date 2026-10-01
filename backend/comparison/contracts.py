"""Shared comparison options and lossless report entries."""

from dataclasses import dataclass, field
from math import isfinite

PRESETS = {
    'strict': {'label': 'Strict matching', 'description': 'Reduce false matches between similar content.',
               'equal_ratio': .98, 'weak_equal_ratio': .85},
    'balanced': {'label': 'Balanced', 'description': 'Everyday revision comparisons.',
                 'equal_ratio': .92, 'weak_equal_ratio': .70},
    'revision': {'label': 'Extensive revision', 'description': 'Find candidates in more heavily edited content.',
                'equal_ratio': .85, 'weak_equal_ratio': .55},
}
MAX_SHEETS = 100
MAX_COLUMNS = 100
MAX_ROWS = 10000
MAX_BLOCKS = 10000
MAX_PAGES = 1000
MAX_CHARACTERS = 2000000
MAX_FUZZY_LENGTH = 2000
MAX_CANDIDATES = 250000


class CompareError(Exception):
    """A sanitized, actionable comparison failure."""

    def __init__(self, detail, code='COMPARE_INVALID'):
        super().__init__(detail)
        self.detail = detail
        self.code = code


@dataclass(frozen=True)
class Options:
    preset: str = 'balanced'
    equal_ratio: float = .92
    weak_equal_ratio: float = .70
    output_type: str = 'word'


@dataclass(frozen=True)
class TextBlock:
    text: str
    location: str


@dataclass(frozen=True)
class Difference:
    change: str
    old: str = ''
    new: str = ''
    old_location: str = ''
    new_location: str = ''
    strength: str = 'none'
    similarity: float | None = None
    field: str = ''


@dataclass
class ComparisonResult:
    family: str
    options: Options
    entries: list[Difference]
    method: str
    warnings: list[str] = field(default_factory=list)

    @property
    def counts(self):
        return {tag: sum(item.change == tag for item in self.entries)
                for tag in ('equal', 'replace', 'insert', 'delete')}


def resolve_options(parameters, family='word'):
    if not isinstance(parameters, dict):
        raise CompareError('Select valid comparison options.')
    preset = parameters.get('preset', 'balanced')
    if not isinstance(preset, str) or preset not in (*PRESETS, 'custom'):
        raise CompareError('Select a supported matching preset.')
    thresholds = parameters if preset == 'custom' else PRESETS[preset]
    equal = thresholds.get('equal_ratio')
    weak = thresholds.get('weak_equal_ratio')
    if any(type(value) not in (int, float) or not isfinite(value) for value in (equal, weak)):
        raise CompareError('Thresholds must be finite numbers.')
    if not 0 < weak <= equal <= 1:
        raise CompareError('Use 0 < possible threshold <= strong threshold <= 1.')
    output = parameters.get('output_type', 'excel' if family == 'excel' else 'word')
    if output not in ('word', 'excel'):
        raise CompareError('Select a Word or Excel report.')
    return Options(preset, float(equal), float(weak), output)


def check_limit(condition, detail):
    if condition:
        raise CompareError(detail, 'COMPARE_LIMIT_EXCEEDED')
