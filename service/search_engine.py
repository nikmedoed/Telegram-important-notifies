from rapidfuzz import fuzz
from nltk.tokenize import word_tokenize
from service.nltk_init import stop_words
from service.cache import cache
import string
import pymorphy3

# Создайте объекты для морфологического анализа для английского и русского
morph_en = pymorphy3.MorphAnalyzer()
morph_ru = pymorphy3.MorphAnalyzer(lang='ru')


def normalize(word):
    if word.isalpha():
        if word.isascii():
            normalized_word = morph_en.parse(word)[0].normal_form
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


def find_phrase(query, text):
    query_tokens = tokenize(query)
    text_tokens = tokenize(text)

    total_similarity = 0
    positions = []
    for query_token in query_tokens:
        for i, text_token in enumerate(text_tokens):
            similarity = fuzz.ratio(query_token, text_token)
            if similarity > 85:
                positions.append(i)
                total_similarity += similarity
                break
        # Учёт расстояния между словами
        if len(positions) > 1:
            positions.sort()
            ltt = len(text_tokens)
            s = 0
            for i in range(1, len(positions)):
                s += positions[i] - positions[i - 1] - 2
            total_similarity *= (ltt - (s / (len(positions) - 1))) / ltt
    return total_similarity / len(query_tokens)


def find_queries(queries, text):
    res = {}
    for query in queries:
        results = find_phrase(query, text)
        if results > 55:
            res[query] = round(results, 2)
    return res


if __name__ == "__main__":
    pass
