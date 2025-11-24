from rapidfuzz import fuzz
from nltk.tokenize import word_tokenize
from service.nltk_init import stop_words
from service.cache import Cache
import string
import math
from typing import List, Tuple, Iterable
import pymorphy3
from nltk.tokenize import sent_tokenize
from nltk.stem import WordNetLemmatizer
from service.db.models import ClauseSpec

lemmatizer_en = WordNetLemmatizer()
morph_ru = pymorphy3.MorphAnalyzer(lang='ru')
# Limit tokenization cache to avoid unbounded growth on long-running processes.
cache = Cache(60 * 60 * 24, max_items=5000)

# Thresholds tuned for short phrases (1–3 words) on low-power hardware.
TOKEN_THRESHOLD = 82  # minimal token-level similarity to be considered a match
MIN_COVERAGE = 0.55   # how many query tokens must be matched
WINDOW_MARGIN = 2     # how many extra tokens around the phrase we look at
COMPACT_EXTRA = 2     # extra tokens allowed inside an otherwise contiguous match
TFIDF_MIN = 0.05      # minimal cosine weight to keep a tf-idf signal


def normalize(word):
    if word.isalpha():
        if word.isascii():
            normalized_word = lemmatizer_en.lemmatize(word.lower())
        else:
            normalized_word = morph_ru.parse(word)[0].normal_form
        return normalized_word
    return word


def tokenize(text):
    text = text.lower()
    res = cache.get(text)
    if res:
        return res
    text_tokens = word_tokenize(text)
    text_tokens = [normalize(word)
                   for word in text_tokens if (word not in stop_words
                                               and word not in string.punctuation)]
    cache.set(text, text_tokens)
    return text_tokens


def _build_idf(all_query_tokens):
    """Compute IDF over query tokens to downweight ubiquitous words."""
    df = {}
    total_docs = 0
    for tokens in all_query_tokens:
        seen = set(tokens)
        if not seen:
            continue
        total_docs += 1
        for token in seen:
            df[token] = df.get(token, 0) + 1
    if total_docs == 0:
        return {}
    return {tok: 1 + math.log((1 + total_docs) / (1 + freq)) for tok, freq in df.items()}


def _tfidf_vector(tokens, idf_map):
    """Return sparse tf-idf vector and its norm."""
    if not tokens or not idf_map:
        return {}, 0.0
    tf = {}
    for tok in tokens:
        if tok not in idf_map:
            continue
        tf[tok] = tf.get(tok, 0) + 1
    if not tf:
        return {}, 0.0
    vec = {tok: cnt * idf_map[tok] for tok, cnt in tf.items()}
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return vec, norm


def _cosine_similarity(vec_a, norm_a, vec_b, norm_b):
    if norm_a == 0 or norm_b == 0:
        return 0.0
    # Iterate over smaller vector
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
        norm_a, norm_b = norm_b, norm_a
    dot = 0.0
    for tok, val in vec_a.items():
        dot += val * vec_b.get(tok, 0.0)
    return dot / (norm_a * norm_b)


def _match_tokens(query_tokens: Iterable[str], sentence_tokens: list[str]) -> List[Tuple[str, float, int]]:
    if not query_tokens or not sentence_tokens:
        return []
    used = set()
    matches: list[tuple[str, float, int]] = []
    for qtok in query_tokens:
        best_score = 0.0
        best_pos = None
        for idx, stok in enumerate(sentence_tokens):
            if idx in used:
                continue
            sim = fuzz.ratio(qtok, stok)
            if sim > best_score:
                best_score = sim
                best_pos = idx
                if sim == 100:
                    break
        if best_score >= TOKEN_THRESHOLD and best_pos is not None:
            used.add(best_pos)
            matches.append((qtok, best_score, best_pos))
    return matches


def _bag_token_score(query_tokens, sentence_tokens):
    """
    Match tokens in any order (each text token used once), reward compactness of matches.
    Compactness penalty is based on span width, not strict ordering.
    """
    matches = _match_tokens(query_tokens, sentence_tokens)
    matched = len(matches)
    if matched == 0:
        return 0.0, matches

    coverage = matched / len(query_tokens)
    if coverage < MIN_COVERAGE:
        return 0.0, matches

    avg_sim = sum(s for _, s, _ in matches) / matched
    positions = [pos for _, _, pos in matches]
    span = max(positions) - min(positions) + 1 if matched > 1 else 1
    compactness = matched / span  # 1.0 if all matched tokens are contiguous
    # Keep compactness influence in [0.4, 1.0]
    compact_factor = 0.4 + 0.6 * compactness

    return avg_sim * coverage * compact_factor, matches


def _is_compact_match(query_tokens, matches, allowed_extra=COMPACT_EXTRA):
    if not matches:
        return False
    if len(matches) < len(query_tokens):
        return False
    if len(matches) != len(query_tokens):
        return False
    positions = sorted(pos for _, _, pos in matches)
    span = positions[-1] - positions[0] + 1 if len(positions) > 1 else 1
    extra = span - len(matches)
    return extra <= allowed_extra


def _has_contiguous_permutation(query_tokens, sentence_tokens):
    """Returns True if any contiguous window has exactly the same multiset of tokens (any order)."""
    qlen = len(query_tokens)
    if qlen == 0 or len(sentence_tokens) < qlen:
        return False
    from collections import Counter

    target = Counter(query_tokens)
    window_counter = Counter(sentence_tokens[:qlen])
    if window_counter == target:
        return True
    for i in range(qlen, len(sentence_tokens)):
        out_tok = sentence_tokens[i - qlen]
        window_counter[out_tok] -= 1
        if window_counter[out_tok] == 0:
            del window_counter[out_tok]
        in_tok = sentence_tokens[i]
        window_counter[in_tok] += 1
        if window_counter == target:
            return True
    return False


def find_phrase(
    query,
    text,
    *,
    query_tokens=None,
    idf_map=None,
    query_tfidf=None,
    query_norm=None,
    required_tokens: Iterable[str] | None = None,
):
    query_tokens = query_tokens or tokenize(query)
    if not query_tokens:
        return 0.0
    joined_query = " ".join(query_tokens)
    required_tokens = set(required_tokens or ())

    sentences = sent_tokenize(text)
    max_similarity = 0

    for sentence in sentences:
        sentence_tokens = tokenize(sentence)

        if not sentence_tokens:
            continue

        # Fast path: exact normalized phrase appears as a contiguous span (any order).
        if _has_contiguous_permutation(query_tokens, sentence_tokens):
            return 100.0

        window = len(query_tokens) + WINDOW_MARGIN
        for start in range(len(sentence_tokens)):
            window_tokens = sentence_tokens[start:start + window]
            if not window_tokens:
                break

            bag_score, matches = _bag_token_score(query_tokens, window_tokens)
            if not bag_score:
                continue

            matched_tokens = {qtok for qtok, _, _ in matches}
            if required_tokens and not required_tokens.issubset(matched_tokens):
                continue

            phrase_score = fuzz.partial_ratio(joined_query, " ".join(window_tokens))
            combined = 0.6 * bag_score + 0.4 * phrase_score
            if _is_compact_match(query_tokens, matches):
                combined = max(combined, 100.0)

            if idf_map and query_tfidf:
                tfidf_vec, tfidf_norm = _tfidf_vector(window_tokens, idf_map)
                tfidf_score = _cosine_similarity(query_tfidf, query_norm or 0.0, tfidf_vec, tfidf_norm) * 100
                if tfidf_score >= TFIDF_MIN * 100:
                    combined = 0.6 * combined + 0.4 * tfidf_score

            max_similarity = max(max_similarity, combined)

    return max_similarity


def _parse_clause(raw_clause: str) -> ClauseSpec:
    # Strip "+" from tokens before tokenization to keep required tokens comparable.
    parts = []
    required_tokens = set()
    for raw in raw_clause.split():
        cleaned = raw.lstrip("+")
        parts.append(cleaned)
        if raw.startswith("+") and len(cleaned) > 0:
            normalized = normalize(cleaned.strip().lower())
            if normalized and normalized not in stop_words and normalized not in string.punctuation:
                required_tokens.add(normalized)

    tokens = tokenize(" ".join(parts))
    required_tokens = tuple(sorted(tok for tok in required_tokens if tok in tokens))
    return ClauseSpec(tokens=tuple(tokens), required=required_tokens)


def parse_query_phrase(phrase: str) -> tuple[list[str], tuple[ClauseSpec, ...]]:
    """
    Split phrase into independent clauses (comma-separated) with required tokens (+word).
    Returns flattened tokens (for idf/tfidf) and clause specs.
    """
    raw_clauses = [part.strip() for part in phrase.split(",") if part.strip()]
    if not raw_clauses:
        return [], tuple()
    clauses = tuple(cl for part in raw_clauses if (cl := _parse_clause(part)).tokens)
    if not clauses:
        return [], tuple()
    all_tokens: list[str] = []
    for clause in clauses:
        all_tokens.extend(clause.tokens)
    return all_tokens, clauses


def find_queries(queries, text):
    res = {}
    if not queries:
        return res

    # If passed a channel search context.
    ctx_query_ids = getattr(queries, "query_ids", None)
    if ctx_query_ids is not None:
        query_ids = tuple(ctx_query_ids)
        entries_map = getattr(queries, "entries_map", None) or {}
        idf_map = getattr(queries, "idf_map", None) or {}
        tfidf_map = getattr(queries, "tfidf_map", None) or {}
        if not query_ids or not entries_map:
            return res

        for qid in query_ids:
            entry = entries_map.get(qid)
            if not entry:
                continue
            phrase = entry.phrase
            clauses = entry.clauses or (ClauseSpec(tokens=tuple(entry.tokens), required=tuple()),)
            clause_vectors = tfidf_map.get(qid, ())
            if not clause_vectors:
                clause_vectors = tuple(_tfidf_vector(cl.tokens, idf_map) for cl in clauses)
            clause_scores = []
            for idx, clause in enumerate(clauses):
                vec, norm = clause_vectors[idx] if idx < len(clause_vectors) else _tfidf_vector(clause.tokens, idf_map)
                score = find_phrase(
                    phrase,
                    text,
                    query_tokens=clause.tokens,
                    idf_map=idf_map,
                    query_tfidf=vec,
                    query_norm=norm,
                    required_tokens=clause.required,
                )
                clause_scores.append(score)
            if clause_scores and min(clause_scores) >= 55:
                res[phrase] = round(min(clause_scores), 2)
        return res

    # Otherwise assume an iterable of phrases (fallback path).
    phrases = list(queries)
    if not phrases:
        return res
    specs = []
    for phrase in phrases:
        tokens, clauses = parse_query_phrase(phrase)
        if not clauses:
            continue
        specs.append((phrase, tokens, clauses))
    if not specs:
        return res
    idf_map = _build_idf((tokens for _, tokens, _ in specs))
    for phrase, tokens, clauses in specs:
        clause_vectors = tuple(_tfidf_vector(cl.tokens, idf_map) for cl in clauses)
        clause_scores = []
        for clause, (vec, norm) in zip(clauses, clause_vectors):
            score = find_phrase(
                phrase,
                text,
                query_tokens=clause.tokens,
                idf_map=idf_map,
                query_tfidf=vec,
                query_norm=norm,
                required_tokens=clause.required,
            )
            clause_scores.append(score)
        if clause_scores and min(clause_scores) >= 55:
            res[phrase] = round(min(clause_scores), 2)
    return res


if __name__ == "__main__":
    pass
