"""
Synonym expander for scientific/medical query terms using NLTK WordNet.
Expands meaningful query keywords with synonyms to improve search recall.
"""

import logging
import re
import string

try:
    import nltk
    from nltk.corpus import wordnet, stopwords

    # Download required NLTK data if not present
    def _ensure_nltk_data():
        for resource, path in [
            ("wordnet", "corpora/wordnet"),
            ("omw-1.4", "corpora/omw-1.4"),
            ("stopwords", "corpora/stopwords"),
        ]:
            try:
                nltk.data.find(path)
            except LookupError:
                nltk.download(resource, quiet=True)

    _ensure_nltk_data()
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    logging.warning("nltk not available; synonym expansion disabled.")

# Generic/filler words that should never receive synonym expansion
_GENERIC_TERMS = {
    "and", "or", "the", "a", "an", "in", "of", "for", "to", "with",
    "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "study", "studies", "research", "analysis", "review",
    "paper", "article", "association", "effect", "effects", "impact",
    "relationship", "between", "among", "using", "based", "related",
    "new", "old", "high", "low", "large", "small", "role", "use",
    "from", "on", "at", "by", "as", "it", "its", "that", "this",
    "these", "those", "which", "what", "who", "how", "when", "where",
}

# Maximum synonyms to add per term (to keep query manageable)
_MAX_SYNONYMS_PER_TERM = 2


def _get_synonyms(word: str) -> list[str]:
    """
    Retrieve synonyms for a word using WordNet.
    Returns a deduplicated list excluding the original word.
    """
    if not NLTK_AVAILABLE:
        return []

    synonyms: set[str] = set()
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            name = lemma.name().lower().replace("_", " ")
            if name != word.lower() and " " not in name:
                synonyms.add(name)

    return list(synonyms)[:_MAX_SYNONYMS_PER_TERM]


def _is_stopword(word: str) -> bool:
    """Check if a word is a stopword or generic term."""
    lower = word.lower()
    if lower in _GENERIC_TERMS:
        return True
    if NLTK_AVAILABLE:
        try:
            sw = set(stopwords.words("english"))
            if lower in sw:
                return True
        except Exception:
            pass
    return False


def expand_query(query: str) -> str:
    """
    Expand a search query by appending synonyms for meaningful terms.

    Each significant term gets up to _MAX_SYNONYMS_PER_TERM synonyms appended
    using OR logic so the search engine can match any variant.

    Args:
        query: Original search query string.

    Returns:
        Expanded query string. Falls back to original query if expansion fails.
    """
    if not NLTK_AVAILABLE:
        return query

    try:
        # Tokenise: split on whitespace, strip punctuation
        tokens = [t.strip(string.punctuation) for t in query.split()]
        tokens = [t for t in tokens if t]

        expanded_parts: list[str] = []
        expanded_count = 0

        for token in tokens:
            if _is_stopword(token):
                expanded_parts.append(token)
                continue

            synonyms = _get_synonyms(token)
            if synonyms:
                # Build "(original OR syn1 OR syn2)" group
                group = " OR ".join([token] + synonyms)
                expanded_parts.append(f"({group})")
                expanded_count += 1
                logging.debug("Expanded '%s' → %s", token, synonyms)
            else:
                expanded_parts.append(token)

        expanded_query = " ".join(expanded_parts)

        if expanded_count:
            logging.info(
                "Query expanded: %d term(s) got synonyms. Original: %r → Expanded: %r",
                expanded_count,
                query,
                expanded_query,
            )
        else:
            logging.info("No synonyms found for query: %r", query)

        return expanded_query

    except Exception as exc:
        logging.warning("Synonym expansion failed, using original query. Error: %s", exc)
        return query
