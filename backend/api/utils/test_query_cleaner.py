#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test query cleaning functionality.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.utils.query_cleaner import clean_query, clean_query_for_pubmed


def test_remove_stop_words():
    """Test removal of common stop words."""
    query = "what is the relationship between vaccines and autism in children"
    result = clean_query(query)
    
    print("Test 1: Remove stop words")
    print(f"  Original: {query}")
    print(f"  Cleaned:  {result}")
    
    # Check that content words are preserved
    assert "relationship" in result.lower()
    assert "vaccines" in result.lower()
    assert "autism" in result.lower()
    assert "children" in result.lower()
    
    # Check that stop words are removed
    assert "what" not in result.lower()
    assert " is " not in result.lower()
    assert " the " not in result.lower()
    assert " between " not in result.lower()
    assert " and " not in result.lower()
    assert " in " not in result.lower()
    
    print("  [PASS]\n")


def test_preserve_important_terms():
    """Test that important scientific terms are preserved."""
    query = "Do vaccines cause autism and affect immune system development"
    result = clean_query(query)
    
    print("Test 2: Preserve important terms")
    print(f"  Original: {query}")
    print(f"  Cleaned:  {result}")
    
    # All key terms should be preserved
    assert "vaccines" in result.lower()
    assert "cause" in result.lower()
    assert "autism" in result.lower()
    assert "affect" in result.lower()
    assert "immune" in result.lower()
    assert "system" in result.lower()
    assert "development" in result.lower()
    
    print("  [PASS]\n")


def test_empty_query():
    """Test with empty query."""
    query = ""
    result = clean_query(query)
    
    print("Test 3: Empty query")
    print(f"  Original: '{query}'")
    print(f"  Cleaned:  '{result}'")
    
    assert result == ""
    print("  [PASS]\n")


def test_only_stop_words():
    """Test query with only stop words."""
    query = "the and or a is"
    result = clean_query(query)
    
    print("Test 4: Query with only stop words")
    print(f"  Original: {query}")
    print(f"  Cleaned:  '{result}'")
    
    # Should result in empty string
    assert result == ""
    print("  [PASS]\n")


def test_punctuation_removal():
    """Test that punctuation is properly removed."""
    query = "What are the side-effects of vaccination? Is it dangerous?"
    result = clean_query(query)
    
    print("Test 5: Punctuation removal")
    print(f"  Original: {query}")
    print(f"  Cleaned:  {result}")
    
    # Hyphens within words should be preserved
    assert "side-effects" in result.lower()
    # But punctuation marks should be gone
    assert "?" not in result
    
    print("  [PASS]\n")


def test_complex_medical_query():
    """Test with complex medical query."""
    query = "Can coronavirus cause long-term neurological complications and brain damage in patients"
    result = clean_query(query)
    
    print("Test 6: Complex medical query")
    print(f"  Original: {query}")
    print(f"  Cleaned:  {result}")
    
    # Key medical terms should be preserved
    assert "coronavirus" in result.lower()
    assert "long-term" in result.lower()
    assert "neurological" in result.lower()
    assert "complications" in result.lower()
    assert "brain" in result.lower()
    assert "damage" in result.lower()
    
    # Stop words removed
    assert result.count(" ") < query.count(" ")  # Should have fewer spaces
    
    print("  [PASS]\n")


def test_pubmed_fallback():
    """Test PubMed query doesn't become empty after cleaning."""
    # Only stop words
    query = "the and or is"
    result = clean_query_for_pubmed(query)
    
    print("Test 7: PubMed fallback to original")
    print(f"  Original: {query}")
    print(f"  Result:   {result}")
    
    # Should return original since cleaning would result in empty
    assert result == query
    print("  [PASS]\n")


def test_reduction_percentage():
    """Test that verbose queries are properly reduced."""
    query = "what are the effects and side effects of the vaccine and the symptoms that can occur in people who have been vaccinated"
    result = clean_query(query)
    
    print("Test 8: Query reduction")
    print(f"  Original: {query} ({len(query.split())} words)")
    print(f"  Cleaned:  {result} ({len(result.split())} words)")
    
    # Query should be significantly shorter
    assert len(result.split()) < len(query.split()) * 0.7  # Less than 70% of original
    print("  [PASS]\n")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing Query Cleaner")
    print("=" * 70 + "\n")
    
    test_remove_stop_words()
    test_preserve_important_terms()
    test_empty_query()
    test_only_stop_words()
    test_punctuation_removal()
    test_complex_medical_query()
    test_pubmed_fallback()
    test_reduction_percentage()
    
    print("=" * 70)
    print("All tests passed!")
    print("=" * 70)
