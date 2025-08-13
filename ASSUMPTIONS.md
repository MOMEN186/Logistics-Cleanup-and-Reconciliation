# Assumptions

This document outlines the assumptions, rules, and heuristics used in this project for data normalization, deduplication, and handling conflicts.

---

## 1. Normalization Rules

1. **Case Normalization**
   - All text fields are converted to lowercase for consistent comparison.
   - Leading and trailing whitespace is removed.

2. **Whitespace Normalization**
   - Consecutive spaces are replaced with a single space.
   - Tabs and newline characters are stripped from string fields.

3. **Special Characters**
   - Non-alphanumeric characters (except `-`, `_`, and `.`) are removed from key identifiers.
   - Unicode characters are normalized to NFC form.

4. **Date & Time**
   - Dates are converted to ISO 8601 format (`YYYY-MM-DD`).
   - Timezones are standardized to UTC unless otherwise specified.

5. **Numeric Fields**
   - All numeric fields are cast to the correct type (integer or float).
   - Missing numeric values are represented as `null` or `NaN`.

---

## 2. Deduplication Heuristic

1. **Primary Key Deduplication**
   - Records with the same unique identifier (e.g., `id` or `email`) are considered duplicates.

2. **Fuzzy Matching**
   - For text fields without unique identifiers, fuzzy matching (e.g., Levenshtein distance ≤ 2) may be used to identify duplicates.
   
3. **Subset Matching**
   - If one record’s fields are a subset of another record’s fields, the more complete record is retained.

---

## 3. Tie-Breakers

1. **Timestamp Priority**
   - If duplicates exist, the record with the most recent `updated_at` or `created_at` timestamp is retained.

2. **Completeness**
   - If timestamps are identical or unavailable, the record with the most non-null fields is preferred.

3. **Alphabetical Order**
   - If the above criteria do not break the tie, the record with the lexicographically smaller primary field (e.g., name or ID) is chosen.

---

## Notes

- All normalization rules are applied **before** deduplication.
- Deduplication and tie-breaking rules are deterministic and should yield consistent results.
- Any deviation from these rules should be documented in the code or in future updates to this file.
