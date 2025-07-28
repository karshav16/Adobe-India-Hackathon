# app/extractor.py
import fitz                   # PyMuPDF
from collections import defaultdict, Counter
import logging
import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Enhanced thresholds
FOOTER_RATIO = 0.90          # bottom 10%
HEADER_RATIO = 0.08          # top 8%
REPEAT_THRESH = 0.50         # >50% pages → header/footer
MIN_FONT_SIZE = 6            # Skip very small text (likely footnotes)
MAX_FONT_SIZE = 72           # Skip very large text (likely graphics)

def _clean_text(text):
    """Clean and normalize text"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Remove control characters
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    return text

def _is_likely_noise(text, font_size):
    """Detect likely noise/irrelevant text"""
    text = text.strip()
    
    # Skip empty or very short text
    if len(text) < 2:
        return True
    
    # Skip if font size is too small or too large
    if font_size < MIN_FONT_SIZE or font_size > MAX_FONT_SIZE:
        return True
    
    # Skip if mostly non-alphabetic characters
    alpha_ratio = sum(1 for c in text if c.isalpha()) / len(text)
    if alpha_ratio < 0.3 and len(text) > 20:
        return True
    
    # Skip common noise patterns
    noise_patterns = [
        r'^\d+$',                           # Just numbers
        r'^[^\w\s]*$',                      # Just symbols
        r'^www\.',                          # URLs
        r'@.*\.com',                        # Email addresses
        r'^\d{1,3}$',                       # Page numbers
        r'^[IVXLCDMivxlcdm]+$',            # Roman numerals only
    ]
    
    for pattern in noise_patterns:
        if re.match(pattern, text):
            return True
    
    return False

def _merge_overlapping_spans(spans):
    """Merge spans that are very close together"""
    if not spans:
        return []
    
    # Sort by x position
    spans.sort(key=lambda s: s["bbox"][0])
    merged = [spans[0]]
    
    for current in spans[1:]:
        last = merged[-1]
        
        # Check if spans overlap or are very close
        if (current["bbox"][0] <= last["bbox"][2] + 2 and  # Close horizontally
            abs(current["bbox"][1] - last["bbox"][1]) <= 2):  # Same baseline
            
            # Merge spans
            merged_bbox = [
                min(last["bbox"][0], current["bbox"][0]),
                min(last["bbox"][1], current["bbox"][1]),
                max(last["bbox"][2], current["bbox"][2]),
                max(last["bbox"][3], current["bbox"][3])
            ]
            
            merged_text = last["text"] + " " + current["text"]
            merged_size = max(last["size"], current["size"])
            merged_bold = last.get("flags", 0) & 64 or current.get("flags", 0) & 64
            
            merged[-1] = {
                "text": merged_text,
                "bbox": merged_bbox,
                "size": merged_size,
                "font": current["font"],  # Use last font
                "flags": merged_bold
            }
        else:
            merged.append(current)
    
    return merged

def load_pdf_lines(path: str, max_pages: int = 50) -> list[dict]:
    """
    Enhanced PDF line extraction with better text processing
    Returns a list of dicts, each representing one visual line:
      {text, page, font_size, bold, x0, y0, x1, y1, page_width}
    """
    try:
        doc = fitz.open(path)
    except Exception as e:
        logging.error(f"Failed to open PDF {path}: {e}")
        return []
    
    pages_to_process = range(min(doc.page_count, max_pages))
    all_lines = []
    hf_counter = Counter()
    
    logging.info(f"Processing {len(pages_to_process)} pages from {path}")
    
    for page_num in pages_to_process:
        try:
            page = doc.load_page(page_num)
            page_width, page_height = page.rect.width, page.rect.height
            
            # Get text with detailed formatting
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if block["type"] != 0:  # Skip image blocks
                    continue
                
                # Group spans by baseline (y-coordinate)
                lines_by_baseline = defaultdict(list)
                
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Skip very small or very large fonts
                        if span["size"] < MIN_FONT_SIZE or span["size"] > MAX_FONT_SIZE:
                            continue
                        
                        # Clean text
                        clean_text = _clean_text(span["text"])
                        if not clean_text or _is_likely_noise(clean_text, span["size"]):
                            continue
                        
                        # Group by rounded baseline
                        baseline = round(span["bbox"][1], 1)
                        lines_by_baseline[baseline].append({
                            "text": clean_text,
                            "bbox": span["bbox"],
                            "size": span["size"],
                            "font": span["font"],
                            "flags": span.get("flags", 0)
                        })
                
                # Process each baseline group
                for baseline, spans in lines_by_baseline.items():
                    if not spans:
                        continue
                    
                    # Merge overlapping spans
                    merged_spans = _merge_overlapping_spans(spans)
                    
                    # Sort spans left to right
                    merged_spans.sort(key=lambda s: s["bbox"][0])
                    
                    # Combine text from all spans on this line
                    line_text = " ".join(span["text"].strip() for span in merged_spans if span["text"].strip())
                    line_text = _clean_text(line_text)
                    
                    if not line_text or len(line_text) < 2:
                        continue
                    
                    # Skip if this looks like noise
                    if _is_likely_noise(line_text, max(s["size"] for s in merged_spans)):
                        continue
                    
                    # Calculate line properties
                    max_font_size = max(span["size"] for span in merged_spans)
                    is_bold = any(("bold" in span["font"].lower()) or (span.get("flags", 0) & 64) 
                                for span in merged_spans)
                    
                    # Bounding box for the entire line
                    min_x = min(span["bbox"][0] for span in merged_spans)
                    max_x = max(span["bbox"][2] for span in merged_spans)
                    min_y = min(span["bbox"][1] for span in merged_spans)
                    max_y = max(span["bbox"][3] for span in merged_spans)
                    
                    line_data = {
                        "text": line_text,
                        "page": page_num + 1,
                        "font_size": round(max_font_size, 2),
                        "bold": is_bold,
                        "x0": round(min_x, 1),
                        "y0": round(min_y, 1),
                        "x1": round(max_x, 1),
                        "y1": round(max_y, 1),
                        "page_width": round(page_width, 1)
                    }
                    
                    all_lines.append(line_data)
                    
                    # Check if this might be a header/footer
                    relative_y = min_y / page_height
                    if relative_y < HEADER_RATIO or relative_y > FOOTER_RATIO:
                        # Normalize text for header/footer detection
                        normalized_text = re.sub(r'\d+', '#', line_text.lower().strip())
                        hf_counter[normalized_text] += 1
        
        except Exception as e:
            logging.warning(f"Error processing page {page_num + 1}: {e}")
            continue
    
    doc.close()
    
    # Remove repeating headers/footers
    total_pages = len(pages_to_process)
    repeated_texts = {
        text for text, count in hf_counter.items() 
        if count >= total_pages * REPEAT_THRESH and len(text.strip()) > 0
    }
    
    # Filter out headers/footers
    filtered_lines = []
    removed_count = 0
    
    for line in all_lines:
        normalized_text = re.sub(r'\d+', '#', line["text"].lower().strip())
        if normalized_text in repeated_texts:
            removed_count += 1
            continue
        
        # Additional filtering
        text = line["text"].strip()
        
        # Skip lines that are just page numbers
        if re.match(r'^\d{1,4}', text):
            removed_count += 1
            continue
        
        # Skip lines with just symbols or very short content
        if len(text) < 3 and not any(c.isalnum() for c in text):
            removed_count += 1
            continue
        
        filtered_lines.append(line)
    
    # Sort lines by page and position
    filtered_lines.sort(key=lambda x: (x["page"], x["y0"]))
    
    logging.info(f"Extracted {len(filtered_lines)} lines, removed {removed_count} headers/footers/noise")
    
    return filtered_lines