"""Bounded, database-assisted fuzzy search for the people directory."""

from difflib import SequenceMatcher
import re
import unicodedata

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from .models import People


MAX_QUERY_LENGTH = 100
MAX_CANDIDATES = 500


def rank_people(queryset: QuerySet[People], search_text: str) -> QuerySet[People] | list[People]:
    """Return relevant people ordered by deterministic similarity."""
    query = search_text.strip()
    direct = queryset.filter(_field_filter(query))
    if direct.exists():
        return _rank_direct_matches(direct, query)
    candidates = list(queryset.filter(_fuzzy_candidate_filter(query))[:MAX_CANDIDATES])
    ranked = [(person, _person_score(person, query)) for person in candidates]
    accepted = [item for item in ranked if item[1] > 0]
    accepted.sort(key=_result_sort_key)
    return [person for person, _ in accepted]


def _rank_direct_matches(queryset: QuerySet[People], query: str) -> QuerySet[People]:
    ranking = Case(
        When(name__iexact=query, then=Value(1040)),
        When(person_id__iexact=query, then=Value(1020)),
        When(email__iexact=query, then=Value(1010)),
        When(name__istartswith=query, then=Value(940)),
        When(person_id__istartswith=query, then=Value(920)),
        When(email__istartswith=query, then=Value(910)),
        When(name__icontains=query, then=Value(840)),
        When(person_id__icontains=query, then=Value(820)),
        default=Value(810),
        output_field=IntegerField(),
    )
    return queryset.annotate(search_rank=ranking).order_by("-search_rank", "name", "person_id")


def _field_filter(value: str) -> Q:
    return Q(name__icontains=value) | Q(person_id__icontains=value) | Q(email__icontains=value)


def _fuzzy_candidate_filter(query: str) -> Q:
    fragments = _candidate_fragments(query)
    candidate_filter = Q(pk__in=[])
    for fragment in fragments:
        candidate_filter |= _field_filter(fragment)
    return candidate_filter


def _candidate_fragments(value: str) -> list[str]:
    words = re.findall(r"[\w@.-]+", value.casefold(), flags=re.UNICODE)
    fragments: list[str] = []
    for word in words:
        size = 2 if len(word) < 6 else 3
        fragments.extend(word[index : index + size] for index in range(len(word) - size + 1))
    return list(dict.fromkeys(fragment for fragment in fragments if len(fragment) >= 2))[:16]


def _person_score(person: People, query: str) -> int:
    normalized_query = _normalize(query)
    scores = [
        _field_score(_normalize(person.name), normalized_query, 40),
        _field_score(_normalize(person.person_id), normalized_query, 20),
        _field_score(_normalize(person.email), normalized_query, 10),
    ]
    return max(scores)


def _field_score(value: str, query: str, weight: int) -> int:
    if not value or not query:
        return 0
    if value == query:
        return 1000 + weight
    if value.startswith(query):
        return 900 + weight
    if query in value:
        return 800 + weight
    ratio = _best_similarity(value, query)
    threshold = 0.72 if len(query) < 5 else 0.62
    return round(600 * ratio) + weight if ratio >= threshold else 0


def _best_similarity(value: str, query: str) -> float:
    values = [value, *value.split()]
    return max(SequenceMatcher(None, candidate, query, autojunk=False).ratio() for candidate in values)


def _normalize(value: str) -> str:
    translated = value.casefold().translate(str.maketrans({"ı": "i", "ł": "l"}))
    decomposed = unicodedata.normalize("NFKD", translated)
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).split())


def _result_sort_key(item: tuple[People, int]) -> tuple[int, str, str]:
    person, score = item
    return -score, _normalize(person.name), person.person_id
