# Weighted Source Aggregation Implementation

## Overview
Implemented a source-by-source weighted aggregation system for fact-checking results. Instead of relying on a single AI-generated final verdict, the system now:

1. Gets individual verdicts from the AI for each source with per-source reliability ratings
2. Filters out very low-reliability sources (< 0.3 reliability threshold)
3. Calculates a weighted aggregated verdict based on source reliability ratings
4. Computes a weighted agreement score reflecting how many high-reliability sources agree

## Changes Made

### 1. Updated `backend/api/utils/ai_calls.py`

#### Modified Data Structures
- **ComparisonResult** dataclass now includes:
  - `source_reliability_scores: dict[str, float]` - Maps source titles to their reliability ratings
  - `weighted_verdict: FactCheckResult | None` - The verdict from weighted aggregation

#### Updated LLM Prompt
- Added `reliability` field (0.0-1.0) to both `individual_results` and `sorted_results`
- Added guidelines for AI to consider:
  - Source quality and scientific rigor
  - Publication status and peer-review
  - Relevance to the claim
  - Distinction between "confidence" (verdict certainty) and "reliability" (source trustworthiness)
- Updated sorting to be by reliability (highest first) instead of confidence

#### New Aggregation Function: `_aggregate_source_verdicts()`
```python
def _aggregate_source_verdicts(
    individual_results: list[dict[str, Any]],
    min_reliability_threshold: float = 0.3,
) -> tuple[FactCheckResult, float, dict[str, float]]
```

**Algorithm:**
1. Filter sources with reliability >= `min_reliability_threshold` (default 0.3)
2. Weight each source's verdict by its reliability score
3. Convert verdicts to numeric values:
   - "verified" → 1.0
   - "partially_verified" → 0.5
   - "conflicting" → 0.5
   - "unverifiable" → 0.25
   - "false" → 0.0
4. Calculate weighted average: `sum(verdict_value * weight) / sum(weights)`
5. Map averaged score to final verdict:
   - >= 0.75 → VERIFIED
   - >= 0.6 → PARTIALLY_VERIFIED
   - <= 0.25 → FALSE
   - 0.25 < score < 0.6 → UNVERIFIABLE
6. Calculate weighted agreement score based on sources supporting the final verdict

#### Modified `check_facts_with_ai()` Function
- Now calls `_aggregate_source_verdicts()` to compute the final verdict
- Returns aggregated verdict instead of AI's direct final_verdict
- Includes source reliability scores in the response
- Has error handling for aggregation failures

### 2. Created Test Suite: `backend/api/utils/test_aggregation.py`

Comprehensive tests covering:
- **Test 1:** All sources verified → Verdict is VERIFIED with high agreement
- **Test 2:** Mixed sources → High-reliability source verdict wins
- **Test 3:** Low-reliability filtering → Very unreliable sources excluded from calculation
- **Test 4:** Conflicting sources → Results in UNVERIFIABLE with moderate agreement
- **Test 5:** Empty results → Defaults to UNVERIFIABLE with zero agreement

All tests pass successfully.

## How It Works

### Example Scenario 1: Consensus with Different Reliability
```
Source A (Reliability: 0.95): VERIFIED
Source B (Reliability: 0.20): FALSE
Source C (Reliability: 0.85): VERIFIED

Processing:
1. Source B filtered (reliability < 0.3)
2. Weighted average: (1.0 × 0.95 + 1.0 × 0.85) / (0.95 + 0.85) = 1.0
3. Result: VERIFIED (sources A and C agree, B was unreliable)
```

### Example Scenario 2: Conflicting Reliable Sources
```
Source A (Reliability: 0.85): VERIFIED
Source B (Reliability: 0.80): FALSE

Processing:
1. Both retained (both > 0.3)
2. Weighted average: (1.0 × 0.85 + 0.0 × 0.80) / (0.85 + 0.80) = 0.515
3. Result: UNVERIFIABLE (sources conflict with similar reliability)
4. Agreement: Low (0.52)
```

### Example Scenario 3: Clear Consensus
```
Source A (Reliability: 0.90): VERIFIED
Source B (Reliability: 0.88): VERIFIED
Source C (Reliability: 0.85): VERIFIED

Processing:
1. All retained
2. Weighted average: 1.0
3. Result: VERIFIED
4. Agreement: 1.0 (perfect agreement)
```

## Key Improvements

1. **No Single Point of Failure**: Results are not determined by a single AI call
2. **Reliability-Weighted**: High-quality sources influence the verdict more
3. **Outlier Filtering**: Very low-quality sources are excluded (< 0.3 threshold)
4. **Transparent Agreement**: Agreement score reflects actual source consensus
5. **Confidence vs Reliability**: Distinguishes between verdict certainty and source trustworthiness
6. **Backward Compatible**: Existing API responses still include all AI-provided data

## Integration Points

The aggregation is transparent to the rest of the system:
- `FactCheckerService` in `backend/api/services/fact_checker.py` continues to work unchanged
- The modified `check_facts_with_ai()` function returns the same response structure
- Clients receive `final_verdict` (now aggregated) and `agreement_score` (now weighted)
- Additional `source_reliability_scores` dict is available for detailed analysis

## Future Enhancements

Possible extensions:
- Configurable reliability thresholds per use case
- Source authority metrics (peer-review status, publication rank)
- Time-decay for source freshness
- Domain-specific reliability weights
- Interactive source conflict resolution UI

## Testing

Run the aggregation tests:
```bash
python backend/api/utils/test_aggregation.py
```

All tests pass and validate the weighted aggregation logic against various scenarios.
