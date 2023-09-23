import os
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize


NLTK_LANGUAGE = os.getenv('NLTK_LANGUAGE')
try:
    words = word_tokenize("This is a test sentence.")
except LookupError:
    nltk.download('punkt')
try:
    stop_words = set(stopwords.words(NLTK_LANGUAGE))
except LookupError:
    nltk.download('stopwords')
    stop_words = set(stopwords.words("russian"))
