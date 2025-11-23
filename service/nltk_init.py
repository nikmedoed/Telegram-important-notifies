import os
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.data import find
from typing import Optional


def _ensure_resource(resource_name: str, download_name: Optional[str] = None) -> None:
    """Make sure the required NLTK resource is present before actual work starts."""
    try:
        find(resource_name)
    except LookupError:
        nltk.download(download_name or resource_name.split('/')[-1])


NLTK_LANGUAGE = os.getenv('NLTK_LANGUAGE', 'russian')

_ensure_resource('tokenizers/punkt', 'punkt')
_ensure_resource('tokenizers/punkt_tab', 'punkt_tab')
_ensure_resource('corpora/wordnet', 'wordnet')
_ensure_resource('corpora/omw-1.4', 'omw-1.4')

# Trigger tokenizer init to make sure punkt downloads happened before runtime usage
word_tokenize("warm up")

try:
    stop_words = set(stopwords.words(NLTK_LANGUAGE))
except LookupError:
    nltk.download('stopwords')
    stop_words = set(stopwords.words("russian"))
