# AI Notes

This document summarizes interactions with GPT for this project.

---

| Prompt | What I Changed | Reason |
|--------|----------------|--------|
| Write a Python script to normalize text fields in a dataset, remove duplicates, and apply tie-breaking rules. | Added date formatting, numeric field handling, and explicit Unicode normalization. | GPT initially handled only strings; my dataset included dates and numbers that also needed normalization. |
| Generate a README.md for my Python project including setup instructions, dependencies, and virtual environment setup. | Added exact commands for Windows PowerShell and Linux/macOS. | GPT’s original README had only generic commands, which could confuse users on different platforms. |
| Create an ASSUMPTIONS.md describing deduplication heuristics, normalization rules, and tie-breakers. | Specified fuzzy matching, completeness checks, and lexicographic tie-breaking. | GPT initially suggested only primary key deduplication, which didn’t cover all cases in my dataset. |

---

## GPT Mistakes & Fixes

**Mistake:** GPT suggested that Python automatically handled Unicode normalization for text fields.  
**Fix:** Explicitly added `unicodedata.normalize('NFC', text)` in the normalization pipeline to ensure consistent Unicode handling.  

---

*End of Notes*
