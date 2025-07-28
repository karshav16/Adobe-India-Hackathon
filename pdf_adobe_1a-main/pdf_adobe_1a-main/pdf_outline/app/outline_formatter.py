# app/outline_formatter.py
import json
import logging
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def _validate_outline_structure(outline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate and fix outline structure"""
    if not outline:
        return []
    
    validated = []
    
    for item in outline:
        # Ensure required fields exist
        if not all(key in item for key in ["level", "text", "page"]):
            logging.warning(f"Skipping invalid outline item: {item}")
            continue
        
        # Validate level format
        level = item["level"]
        if not isinstance(level, str) or not level.startswith("H") or level not in ["H1", "H2", "H3"]:
            logging.warning(f"Invalid level '{level}', defaulting to H1")
            level = "H1"
        
        # Validate text
        text = str(item["text"]).strip()
        if not text:
            logging.warning("Skipping item with empty text")
            continue
        
        # Validate page number
        try:
            page = int(item["page"])
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            logging.warning(f"Invalid page number '{item['page']}', defaulting to 1")
            page = 1
        
        validated.append({
            "level": level,
            "text": text,
            "page": page
        })
    
    return validated

def _ensure_proper_hierarchy(outline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure proper heading hierarchy (H1 -> H2 -> H3)"""
    if not outline:
        return []
    
    corrected = []
    current_levels = {"H1": False, "H2": False, "H3": False}
    
    for item in outline:
        level = item["level"]
        
        # Hierarchy correction logic
        if level == "H1":
            # H1 is always allowed
            current_levels = {"H1": True, "H2": False, "H3": False}
            corrected.append(item)
            
        elif level == "H2":
            # H2 requires H1 to exist
            if not current_levels["H1"]:
                # Promote to H1
                item = {**item, "level": "H1"}
                current_levels = {"H1": True, "H2": False, "H3": False}
            else:
                current_levels["H2"] = True
                current_levels["H3"] = False
            corrected.append(item)
            
        elif level == "H3":
            # H3 requires H2 to exist
            if not current_levels["H2"]:
                if not current_levels["H1"]:
                    # Promote to H1
                    item = {**item, "level": "H1"}
                    current_levels = {"H1": True, "H2": False, "H3": False}
                else:
                    # Promote to H2
                    item = {**item, "level": "H2"}
                    current_levels["H2"] = True
                    current_levels["H3"] = False
            else:
                current_levels["H3"] = True
            corrected.append(item)
    
    return corrected

def _remove_duplicates(outline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate entries while preserving order"""
    seen = set()
    unique_outline = []
    
    for item in outline:
        # Create a key based on level and normalized text
        key = (item["level"], item["text"].lower().strip())
        
        if key not in seen:
            seen.add(key)
            unique_outline.append(item)
        else:
            logging.debug(f"Removing duplicate: {item}")
    
    return unique_outline

def _clean_heading_text(text: str) -> str:
    """Clean and normalize heading text"""
    import re
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Remove trailing punctuation that's not meaningful
    text = re.sub(r'[\.]{2,}$', '', text)  # Remove trailing dots
    text = re.sub(r'[-_]{2,}$', '', text)  # Remove trailing dashes/underscores
    
    # Clean up common formatting artifacts
    text = re.sub(r'\s*[:]\s*$', '', text)  # Remove trailing colons with spaces
    
    return text.strip()

def to_json(title: str, outline: List[Dict[str, Any]]) -> str:
    """
    Enhanced formatter that validates and cleans the outline structure
    """
    # Clean and validate title
    clean_title = str(title).strip() if title else ""
    if not clean_title:
        clean_title = "Untitled Document"
    
    # Process outline
    processed_outline = []
    
    if outline:
        # Step 1: Validate structure
        validated_outline = _validate_outline_structure(outline)
        
        # Step 2: Clean heading text
        for item in validated_outline:
            item["text"] = _clean_heading_text(item["text"])
        
        # Step 3: Remove duplicates
        unique_outline = _remove_duplicates(validated_outline)
        
        # Step 4: Ensure proper hierarchy
        processed_outline = _ensure_proper_hierarchy(unique_outline)
        
        # Step 5: Final validation - remove any items with empty text after cleaning
        processed_outline = [item for item in processed_outline if item["text"]]
    
    # Create final output structure
    output = {
        "title": clean_title,
        "outline": processed_outline
    }
    
    try:
        # Generate JSON with proper formatting
        json_str = json.dumps(
            output, 
            indent=2, 
            ensure_ascii=False,
            separators=(',', ': ')
        )
        
        logging.info(f"Successfully formatted outline: title='{clean_title}', {len(processed_outline)} headings")
        return json_str
        
    except (TypeError, ValueError) as e:
        logging.error(f"JSON serialization error: {e}")
        
        # Return minimal error structure
        error_output = {
            "title": "Error",
            "outline": [],
            "error": f"Failed to format JSON: {str(e)}"
        }
        
        try:
            return json.dumps(error_output, indent=2, ensure_ascii=False)
        except:
            # Absolute fallback
            return '{"title": "Error", "outline": [], "error": "Critical formatting error"}'

def validate_json_output(json_str: str) -> bool:
    """Validate that the output JSON is properly formatted"""
    try:
        data = json.loads(json_str)
        
        # Check required fields
        if "title" not in data or "outline" not in data:
            return False
        
        # Validate title
        if not isinstance(data["title"], str):
            return False
        
        # Validate outline structure
        if not isinstance(data["outline"], list):
            return False
        
        for item in data["outline"]:
            if not isinstance(item, dict):
                return False
            if not all(key in item for key in ["level", "text", "page"]):
                return False
            if item["level"] not in ["H1", "H2", "H3"]:
                return False
            if not isinstance(item["text"], str) or not item["text"].strip():
                return False
            if not isinstance(item["page"], int) or item["page"] < 1:
                return False
        
        return True
        
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return False