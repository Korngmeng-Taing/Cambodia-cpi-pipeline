# Pipeline Maintenance Guide

This document contains technical notes and "gotchas" for maintaining the CPI Pipeline.

## COICOP Classification Regex

The classification pipeline uses PostgreSQL for its data transformations. When defining regex patterns in seeds (e.g., `coicop_critical_traps.csv`, `coicop_text_rules.csv`), be aware of the following:

### Word Boundaries
PostgreSQL does **not** recognize the standard `\b` for word boundaries. 

- **Wrong**: `\btoothpaste\b`
- **Right**: `\ytoothpaste\y`

Using `\b` will result in the regex failing to match, causing products to miss critical traps and fall back to lower-priority classification methods (like store defaults), leading to misclassifications.

Always use `\y` to mark the start or end of a word.
