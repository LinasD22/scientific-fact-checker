"""
Query cleaning utility for PubMed and other API searches.
Removes common English stop words that don't contribute to search relevance.
"""

import logging
import re
from typing import Set

logger = logging.getLogger(__name__)

# Common English stop words (articles, prepositions, conjunctions, pronouns, etc.)
# These words are very common and don't add much value to scientific search queries
STOP_WORDS: Set[str] = {
    # Articles
    "a", "an", "the",
    
    # Conjunctions
    "and", "or", "but", "yet", "nor", "so", "because", "since", "although", "though",
    "if", "while", "when", "where", "whereas", "unless", "until", "before", "after",
    
    # Prepositions
    "in", "on", "at", "by", "from", "to", "for", "with", "of", "about", "as", "into",
    "through", "during", "between", "among", "around", "along", "across", "without",
    "within", "beneath", "above", "below", "over", "under", "off", "up", "down",
    "near", "far", "against", "behind", "before", "after", "above", "below",
    
    # Pronouns
    "i", "me", "you", "he", "she", "it", "we", "they", "them", "him", "her", "us",
    "my", "your", "his", "her", "our", "their", "mine", "yours", "his", "hers",
    "this", "that", "these", "those", "what", "which", "who", "whom", "whose",
    
    # Common verbs that add little value
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "can", "could", "will", "would",
    "shall", "should", "may", "might", "must", "ought", "seems", "appears",
    
    # Other common words
    "there", "here", "then", "now", "not", "no", "yes", "ok", "so", "very",
    "just", "only", "also", "too", "such", "same", "other", "another", "each",
    "every", "both", "either", "any", "all", "some", "few", "many", "much", "more",
    
    # Common question words (usually in user input that shouldn't be in search)
    "how", "why", "what", "when", "where", "which", "can", "should", "does", "do",
    
    # Additional common words
    "more", "most", "less", "least", "said", "say", "says",
}


def clean_query(query: str, min_word_length: int = 2) -> str:
    """
    Clean a search query by removing stop words and extra whitespace.
    
    Args:
        query: The search query string
        min_word_length: Minimum word length to keep (default 2)
    
    Returns:
        Cleaned query string
    """
    if not query:
        return ""
    
    # Convert to lowercase for comparison
    query_lower = query.lower()
    
    # Split into words and keep track of original words
    words = query_lower.split()
    
    cleaned_words = []
    for word in words:
        # Remove punctuation and extra characters (keep only alphanumeric and common punctuation)
        # But preserve hyphens within words (e.g., "co-infection")
        clean_word = re.sub(r'[^\w\-]', '', word)
        
        if not clean_word:
            continue
        
        # Skip stop words
        if clean_word in STOP_WORDS:
            continue
        
        # Skip words that are too short (usually not useful)
        if len(clean_word) < min_word_length:
            continue
        
        cleaned_words.append(clean_word)
    
    # Join cleaned words
    result = " ".join(cleaned_words)
    
    # Log if significant reduction happened
    original_word_count = len(words)
    cleaned_word_count = len(cleaned_words)
    if cleaned_word_count < original_word_count:
        reduction_percent = ((original_word_count - cleaned_word_count) / original_word_count) * 100
        logger.debug(
            f"Query cleaned: {original_word_count} words → {cleaned_word_count} words "
            f"({reduction_percent:.1f}% reduction)\n"
            f"  Original: {query}\n"
            f"  Cleaned:  {result}"
        )
    
    return result


def clean_query_for_pubmed(query: str) -> str:
    """
    Clean a query specifically for PubMed search.
    Removes stop words and ensures the query is optimized for the PubMed API.
    
    Args:
        query: The original search query
    
    Returns:
        Cleaned query suitable for PubMed
    """
    cleaned = clean_query(query, min_word_length=2)
    
    # If query is empty after cleaning, return original to avoid API errors
    if not cleaned:
        logger.warning(f"Query cleaning resulted in empty string. Using original: {query}")
        return query
    
    return cleaned
