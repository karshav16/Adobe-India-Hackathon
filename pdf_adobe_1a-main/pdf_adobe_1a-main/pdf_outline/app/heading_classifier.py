# app/heading_classifier.py
import re
import logging
import numpy as np
from collections import Counter, defaultdict
from .features import enhanced_metrics, enhanced_line_vector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Enhanced patterns
NUMERIC_RE = re.compile(r'^(\d+(?:\.\d+)*)(?:[)\.\-:\s]+)')
BULLET_RE = re.compile(r'^[•·▪▫◦‣⁃]\s+')
SECTION_TITLES = {
    "EDUCATION", "EXPERIENCE", "PROJECTS", "SKILLS", "WORK EXPERIENCE",
    "ACHIEVEMENTS", "RELEVANT COURSEWORK", "CONTACT", "REFERENCES",
    "SUMMARY", "OBJECTIVE", "PROFILE", "QUALIFICATIONS", "CERTIFICATIONS",
    "AWARDS", "PUBLICATIONS", "LANGUAGES", "INTERESTS", "HOBBIES",
    "VOLUNTEER", "ACTIVITIES", "LEADERSHIP", "RESEARCH"
}

# Enhanced probability calculation using multiple factors
def _enhanced_prob(feat: np.ndarray) -> float:
    """
    Enhanced probability calculation with weighted features
    Features: [font_rank, bold, caps_ratio, numeric, ends_colon, centered, 
              left_indent, top_spacing, is_page1, too_long, text_len, 
              whitespace_after, isolation_score, formatting_consistency]
    """
    (font_rank, bold, caps_ratio, numeric, ends_colon, centered, 
     left_indent, top_spacing, is_page1, too_long, text_len, 
     whitespace_after, isolation_score, formatting_consistency) = feat
    
    # Base probability from font ranking
    font_prob = max(0, 0.8 - font_rank * 0.15)  # Decreases with rank
    
    # Style indicators
    style_score = (
        0.4 * bold +                    # Bold text is likely heading
        0.3 * caps_ratio +              # Caps indicate importance
        0.2 * numeric +                 # Numbered sections
        0.15 * ends_colon +             # Section headers often end with :
        0.25 * centered                 # Centered text often headings
    )
    
    # Position indicators
    position_score = (
        0.2 * (1 - left_indent) +      # Less indented = more likely heading
        0.15 * top_spacing +            # More space above = heading
        0.1 * is_page1 +                # Page 1 content more likely headings
        0.2 * whitespace_after +        # Headings often followed by space
        0.25 * isolation_score          # Isolated lines often headings
    )
    
    # Length penalties
    length_penalty = (
        0.8 if text_len < 3 else        # Very short text unlikely heading
        0.9 if text_len < 6 else        # Short text somewhat unlikely
        1.0 if text_len < 60 else       # Good length for headings
        0.7 if text_len < 100 else      # Long text less likely
        0.3                             # Very long text unlikely heading
    )
    
    # Formatting consistency bonus
    consistency_bonus = 0.15 * formatting_consistency
    
    # Combine all factors
    total_prob = (
        0.35 * font_prob +
        0.30 * style_score +
        0.25 * position_score +
        0.10 * consistency_bonus
    ) * length_penalty
    
    # Apply penalties
    if too_long:
        total_prob *= 0.3
    
    return min(total_prob, 0.99)

def _is_likely_title(line, font_rank, page1_lines):
    """Enhanced title detection"""
    text = line["text"].strip()
    
    # Skip section headers
    if text.upper() in SECTION_TITLES:
        return False
        
    # Skip if too short or too long
    word_count = len(text.split())
    if word_count < 2 or word_count > 15:
        return False
    
    # Skip numbered items
    if NUMERIC_RE.match(text) or BULLET_RE.match(text):
        return False
    
    # Prefer larger fonts on page 1
    font_score = font_rank.get(line["font_size"], 10)
    if font_score > 2:  # Not in top 3 font sizes
        return False
    
    # Check position (titles often near top)
    y_position = line["y0"]
    page_height = max(l["y1"] for l in page1_lines if l["page"] == 1)
    relative_pos = y_position / page_height
    
    if relative_pos > 0.5:  # Below middle of page
        return False
    
    return True

def _detect_heading_patterns(candidates):
    """Detect consistent formatting patterns in headings"""
    patterns = defaultdict(list)
    
    for cand in candidates:
        text = cand["text"].strip()
        
        # Categorize by patterns
        if NUMERIC_RE.match(text):
            patterns["numbered"].append(cand)
        elif text.isupper() and len(text.split()) <= 4:
            patterns["all_caps"].append(cand)
        elif cand["bold"]:
            patterns["bold"].append(cand)
        else:
            patterns["other"].append(cand)
    
    return patterns

def _assign_heading_levels(candidates, font_rank):
    """Enhanced heading level assignment"""
    if not candidates:
        return []
    
    # Group by formatting patterns
    patterns = _detect_heading_patterns(candidates)
    
    # Sort candidates by page and position
    sorted_candidates = sorted(candidates, key=lambda x: (x["page"], x["y0"]))
    
    outline = []
    level_tracker = {"H1": False, "H2": False, "H3": False}
    
    for cand in sorted_candidates:
        text = cand["text"].strip()
        font_size = cand["font_size"]
        font_level = font_rank.get(font_size, 10)
        
        # Determine level based on multiple factors
        if NUMERIC_RE.match(text):
            # Numbered headings
            match = NUMERIC_RE.match(text)
            depth = match.group(1).count('.') + 1
            level = f"H{min(depth, 3)}"
        elif text.isupper() and len(text.split()) <= 4:
            # All caps short text = major heading
            level = "H1"
        elif font_level == 0:
            # Largest font
            level = "H1"
        elif font_level == 1:
            # Second largest font
            level = "H2" if level_tracker["H1"] else "H1"
        elif cand["bold"] and font_level <= 2:
            # Bold and reasonably large
            level = "H2" if level_tracker["H1"] else "H1"
        else:
            # Default assignment based on context
            if not level_tracker["H1"]:
                level = "H1"
            elif not level_tracker["H2"]:
                level = "H2"
            else:
                level = "H3"
        
        # Update tracker
        level_tracker[level] = True
        if level == "H1":
            level_tracker["H2"] = level_tracker["H3"] = False
        elif level == "H2":
            level_tracker["H3"] = False
        
        outline.append({
            "level": level,
            "text": text,
            "page": cand["page"]
        })
    
    return outline

def classify(lines):
    """Enhanced classification with improved accuracy"""
    if not lines:
        return "", []
    
    # 1) Enhanced metrics computation
    font_rank, left_x, med_gap, formatting_stats = enhanced_metrics(lines)
    
    # 2) Enhanced feature vectors & probabilities
    feats = np.array([enhanced_line_vector(l, font_rank, left_x, med_gap, formatting_stats, lines) for l in lines])
    probs = np.array([_enhanced_prob(f) for f in feats])
    
    # 3) Dynamic threshold based on document characteristics
    base_threshold = 0.3
    if len(lines) > 100:  # Long document, be more selective
        threshold = base_threshold + 0.1
    else:  # Short document, be more inclusive
        threshold = base_threshold - 0.05
    
    # Get candidates
    cand_idxs = np.where(probs >= threshold)[0]
    candidates = [{**lines[i], "prob": probs[i]} for i in cand_idxs]
    
    # 4) Enhanced title detection
    page1_lines = [ln for ln in lines if ln["page"] == 1]
    page1_lines.sort(key=lambda l: (-l["font_size"], l["y0"]))
    
    title = ""
    for ln in page1_lines:
        if _is_likely_title(ln, font_rank, page1_lines):
            title = ln["text"].strip()
            logging.info(f"Title chosen: '{title}'")
            break
    
    # 5) Fallback title selection
    if not title:
        # Try highest probability candidate on page 1
        p1_cands = [c for c in candidates if c["page"] == 1]
        if p1_cands:
            best = max(p1_cands, key=lambda c: c["prob"])
            if best["prob"] > 0.5:  # Only if reasonably confident
                title = best["text"]
                logging.info(f"Fallback title: '{title}'")
    
    # 6) Remove title from candidates and build outline
    filtered_candidates = []
    for cand in candidates:
        if cand["page"] == 1 and cand["text"].strip() == title:
            continue
        # Additional filtering
        text = cand["text"].strip()
        if len(text) < 2 or len(text) > 200:  # Skip very short/long text
            continue
        if text.upper() in SECTION_TITLES and cand["prob"] < 0.7:  # Be selective with section headers
            continue
        filtered_candidates.append(cand)
    
    # 7) Enhanced heading level assignment
    outline = _assign_heading_levels(filtered_candidates, font_rank)
    
    # 8) Remove duplicates while preserving order
    seen = set()
    final_outline = []
    for item in outline:
        key = (item["level"], item["text"].lower())
        if key not in seen:
            seen.add(key)
            final_outline.append(item)
    
    logging.info(f"Detected {len(final_outline)} headings; title='{title}'")
    return title, final_outline