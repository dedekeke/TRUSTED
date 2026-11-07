"""Detect v3: v2 + a per-column router between name-based kNN (v1) and value-based classifier (v2), plus fixes
found while analysing v2 errors (value distributions for the LLM, honest confidence, Art. 9-aware LLM and recall
bias). Imports v1 and v2, never modifies them."""
__version__ = "3.0"
