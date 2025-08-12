# Simple Unified Scoring System

## Overview

A simple, consistent scoring system that ensures name matches always beat description matches across all plugins.

## Problem Solved

Previously, different plugins used inconsistent scoring where history description matches could score higher than desktop file name matches.

## Simple Solution

### Base Scores
- **Name matches**: 100 points base
- **Description matches**: 50 points base
- **History boost**: +20 points

### Match Quality Bonuses
Within each category (name or description):
- Exact match: +100 points
- Prefix match: +20 points + quality bonus
- Substring match: +10 points + position bonus
- Fuzzy match: quality * 5 points

### Key Principles
1. **Fresh exact matches beat history fuzzy matches**:
   - Fresh name exact: 100 + 100 = 200
   - History name fuzzy: 100 + (quality * 5) + 20 = 125 (assuming average quality)
2. **Any name match beats any description match**:
   - Worst name match: 100 (fuzzy)
   - Best description match: 50 + 100 + 20 = 170 (exact + history)

## Example Scores

**Query: "firefox"**

| Match | Type | Base | Bonus | History | Total |
|-------|------|------|-------|---------|-------|
| Name exact | Fresh | 100 | +100 | - | 200 |
| Name exact | History | 100 | +100 | +20 | 220 |
| Name fuzzy | History | 100 | + (quality*5) | +20 | ~125 |
| Description exact | Fresh | 50 | +100 | - | 150 |
| Description exact | History | 50 | +100 | +20 | 170 |

Result: History name exact (220) > Fresh name exact (200) > History description (170) > Fresh description (150) > History name fuzzy (125)

## Implementation

All plugins now use the same simple functions:
- `score_name_match(query, name)` - for names/titles/commands
- `score_description_match(query, description)` - for descriptions
- `apply_history_boost(score)` - adds +20 for history items

**Files changed:**
- `launcher/utils/scoring_system.py` - Simple scoring functions
- All plugins updated to use these functions consistently