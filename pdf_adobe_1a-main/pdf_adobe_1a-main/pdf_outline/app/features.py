# app/features.py
import re
import math
import numpy as np
from collections import Counter, defaultdict

NUMERIC_RE = re.compile(r'^\d+(?:\.\d+)*[)\.\-:\s]')
BULLET_RE = re.compile(r'^[•·▪▫◦‣⁃]\s+')

def enhanced_metrics(lines):
    """Enhanced metrics computation with additional statistics"""
    if not lines:
        return {}, 0, {}, {}
    
    # Font ranking (0 = largest)
    unique_sizes = sorted({ln["font_size"] for ln in lines}, reverse=True)
    font_rank = {sz: i for i, sz in enumerate(unique_sizes)}
    
    # Common left margin
    left_positions = [round(ln["x0"], 1) for ln in lines]
    left_counter = Counter(left_positions)
    common_left = left_counter.most_common(1)[0][0]
    
    # Median gaps per page
    gaps_by_page = defaultdict(list)
    for page_num in set(l["page"] for l in lines):
        page_lines = [l for l in lines if l["page"] == page_num]
        page_lines.sort(key=lambda x: x["y0"])
        
        for i in range(len(page_lines) - 1):
            gap = page_lines[i+1]["y0"] - page_lines[i]["y1"]
            if gap > 0:  # Only positive gaps
                gaps_by_page[page_num].append(gap)
    
    median_gaps = {}
    for page_num, gaps in gaps_by_page.items():
        if gaps:
            gaps.sort()
            median_gaps[page_num] = gaps[len(gaps) // 2]
        else:
            median_gaps[page_num] = 0
    
    # Additional formatting statistics
    formatting_stats = {
        'bold_fonts': {ln["font_size"] for ln in lines if ln["bold"]},
        'font_usage': Counter(ln["font_size"] for ln in lines),
        'avg_line_length': np.mean([len(ln["text"]) for ln in lines]),
        'page_widths': {ln["page"]: ln["page_width"] for ln in lines},
        'indent_levels': sorted(set(round(ln["x0"], 1) for ln in lines))
    }
    
    return font_rank, common_left, median_gaps, formatting_stats

def enhanced_line_vector(line, font_rank, common_left, median_gaps, formatting_stats, all_lines):
    """Enhanced feature vector with 14 dimensions"""
    text = line["text"].strip()
    page_num = line["page"]
    font_size = line["font_size"]
    
    # Basic features
    rank = font_rank.get(font_size, len(font_rank))
    bold = int(line["bold"])
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    numeric = int(bool(NUMERIC_RE.match(text)))
    ends_colon = int(text.rstrip().endswith(":"))
    
    # Position features
    center_x = (line["x1"] + line["x0"]) / 2
    page_width = line["page_width"]
    page_center = page_width / 2
    centered = int(abs(center_x - page_center) < page_width * 0.15)
    
    left_indent = max(0, min(1, (line["x0"] - common_left) / 100))
    
    # Spacing features
    median_gap = median_gaps.get(page_num, 20)
    
    # Get surrounding lines for context
    page_lines = [l for l in all_lines if l["page"] == page_num]
    page_lines.sort(key=lambda x: x["y0"])
    
    current_idx = next((i for i, l in enumerate(page_lines) if l == line), -1)
    
    # Top spacing
    if current_idx > 0:
        prev_line = page_lines[current_idx - 1]
        top_gap = line["y0"] - prev_line["y1"]
        top_spacing = min(1, max(0, (top_gap - median_gap) / median_gap)) if median_gap > 0 else 0
    else:
        top_spacing = 1  # First line on page
    
    # Whitespace after
    if current_idx < len(page_lines) - 1:
        next_line = page_lines[current_idx + 1]
        bottom_gap = next_line["y0"] - line["y1"]
        whitespace_after = min(1, max(0, (bottom_gap - median_gap) / median_gap)) if median_gap > 0 else 0
    else:
        whitespace_after = 1  # Last line on page
    
    # Additional features
    is_page1 = int(page_num == 1)
    too_long = int(len(text) > 150)
    text_len = len(text)
    
    # Isolation score (how isolated this line is)
    isolation_score = min(1, (top_spacing + whitespace_after) / 2)
    
    # Formatting consistency (how common this font size is for bold text)
    if bold and font_size in formatting_stats['bold_fonts']:
        bold_with_size = sum(1 for l in all_lines if l["bold"] and l["font_size"] == font_size)
        total_bold = sum(1 for l in all_lines if l["bold"])
        formatting_consistency = bold_with_size / max(total_bold, 1)
    else:
        formatting_consistency = formatting_stats['font_usage'][font_size] / len(all_lines)
    
    vector = [
        rank,                    # 0: Font rank (0 = largest)
        bold,                    # 1: Bold text
        caps_ratio,             # 2: Ratio of uppercase characters
        numeric,                # 3: Starts with number
        ends_colon,             # 4: Ends with colon
        centered,               # 5: Horizontally centered
        left_indent,            # 6: Left indentation level
        top_spacing,            # 7: Space above (normalized)
        is_page1,               # 8: On first page
        too_long,               # 9: Text too long for heading
        text_len,               # 10: Text length
        whitespace_after,       # 11: Space below (normalized)
        isolation_score,        # 12: How isolated the line is
        formatting_consistency  # 13: Formatting consistency score
    ]
    
    return np.array(vector)

# Backward compatibility aliases
def compute_common_metrics(lines):
    """Backward compatibility wrapper"""
    font_rank, common_left, median_gaps, _ = enhanced_metrics(lines)
    return font_rank, common_left, median_gaps

def line_features(line, font_rank, common_left, median_gaps):
    """Backward compatibility wrapper - simplified version"""
    text = line["text"].strip()
    page_num = line["page"]
    
    # Basic features matching original
    rank = font_rank.get(line["font_size"], len(font_rank))
    bold = int(line["bold"])
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    numeric = int(bool(NUMERIC_RE.match(text)))
    ends_colon = int(text.rstrip().endswith(":"))
    
    # Position features
    center_x = (line["x1"] + line["x0"]) / 2
    page_width = line["page_width"]
    centered = int(abs(center_x - (common_left + page_width/2)) < page_width * 0.15)
    left_indent = max(0, min(1, (line["x0"] - common_left) / 200))
    
    # Spacing (simplified)
    median_gap = median_gaps.get(page_num, 20)
    top_spacing = min(1, (line["y0"] - median_gap * 1.2) / 200)
    
    # Other features
    is_page1 = int(page_num == 1)
    too_long = int(len(text) > 80)
    text_len_log = math.log1p(len(text))
    
    return [rank, bold, caps_ratio, numeric, ends_colon, centered, 
            left_indent, top_spacing, is_page1, too_long, text_len_log]

# Keep original aliases for backward compatibility
common_metrics = compute_common_metrics
line_vector = line_features