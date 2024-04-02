# Try this libs

- pip install stanza - сильная штука для NLP на нейронках и для русского


```
from gensim.models import Word2Vec

w2v_model.most_similar('university', topn=5)
w2v_model.similarity('jazz', 'music')
w2v_model.doesnt_match(['pine', 'fir', 'coconut'])
save load

# Обычно 99% выборки должно попадать в диапазон ± 3 σ от среднего
```

Посмотреть на более продвинутые штуки для поиска фраз
```python
from stopWordsFilter import stopWfilter

from sklearn.feature_extraction.text import TfidfVectorizer
import pandas as pd

with open('testBase.txt', 'r', encoding='utf-8') as f:
    texts = f.read().replace('\t', '\n\n').split('===')

# normTexts = list(map(lambda x: stopWfilter(x).split(), texts))

normTexts = list(map(stopWfilter, texts))

# tfidf_vectorizer = TfidfVectorizer()
# values = tfidf_vectorizer.fit_transform(normTexts[0])
#
# # Show the Model as a pandas DataFrame
# feature_names = tfidf_vectorizer.get_feature_names()
# pdf = pd.DataFrame(values.toarray(), columns = feature_names)
# print(pdf)

from rake_nltk import Rake
r = Rake()
r.language = "russian"
# Extraction given the text.
for te in texts:
    r.extract_keywords_from_text(te)
    ranked = r.get_ranked_phrases_with_scores()
    print( ranked[:5])
    
###
def format(text):
morph = pymorphy3.MorphAnalyzer()
punc = ["/", "?", "!", ".", ",", " - ", "+", "*", "\"", ":", ";", "(", ")", "—", "«", "»", "…"]
for i in punc:
    text = text.replace(i, "")

# sentences = sent_tokenize(text)
# for i in sentences:
#     print( word_tokenize(i))
return list(map(lambda x: morph.parse(x)[0].normal_form.upper(), text.split()))

```

##### cos dist
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def cosine_similarity_texts(text1, text2):
    vectorizer = TfidfVectorizer().fit_transform([text1, text2])
    vectors = vectorizer.toarray()
    cosine_sim = cosine_similarity(vectors)
    return cosine_sim[0][1]
    
   