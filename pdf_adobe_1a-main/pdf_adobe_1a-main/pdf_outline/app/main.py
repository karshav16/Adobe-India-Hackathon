# app/main.py
import argparse
import os
import logging
import json
import re
from pathlib import Path
from .extractor import load_pdf_lines
from .heading_classifier import classify
from .outline_formatter import to_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def _enhanced_fallback_title(lines):
    """Enhanced fallback title detection"""
    if not lines:
        return ""
    
    page1_lines = [l for l in lines if l["page"] == 1]
    if not page1_lines:
        return ""
    
    # Sort by font size (largest first), then by position (top first)
    page1_lines.sort(key=lambda l: (-l["font_size"], l["y0"]))
    
    # Try to find a good title candidate
    for line in page1_lines:
        text = line["text"].strip()
        
        # Skip if too short or too long
        word_count = len(text.split())
        if word_count < 2 or word_count > 12:
            continue
            
        # Skip numbered items
        if re.match(r'^\d+(\.\d+)*[\.\)\-:\s]', text):
            continue
            
        # Skip common non-title patterns
        if any(pattern in text.lower() for pattern in [
            'page', 'chapter', 'section', 'table of contents',
            'abstract', 'summary', 'introduction'
        ]):
            continue
            
        # Skip if mostly punctuation or numbers
        if len(re.sub(r'[a-zA-Z\s]', '', text)) > len(text) * 0.3:
            continue
            
        # This looks like a reasonable title
        return text
    
    # If no good candidate found, use the largest font text
    if page1_lines:
        return page1_lines[0]["text"].strip()
    
    return ""

def process_single_pdf(pdf_path, output_path):
    """Process a single PDF file"""
    try:
        # Load and process PDF
        lines = load_pdf_lines(pdf_path)
        if not lines:
            logging.error(f"No text extracted from {pdf_path}")
            return False
        
        # Classify headings
        title, outline = classify(lines)
        
        # Enhanced fallback for title
        if not title or len(title.strip()) < 3:
            title = _enhanced_fallback_title(lines)
            if not title:
                title = Path(pdf_path).stem.replace('_', ' ').replace('-', ' ').title()
        
        # Generate JSON output
        json_output = to_json(title, outline)
        
        # Ensure output directory exists
        output_path.parent.mkdir(exist_ok=True, parents=True)
        
        # Write output
        output_path.write_text(json_output, encoding="utf-8")
        logging.info(f"Successfully processed {pdf_path} → {output_path}")
        return True
        
    except Exception as e:
        logging.error(f"Error processing {pdf_path}: {e}")
        return False

def process_directory(input_dir, output_dir):
    """Process all PDFs in input directory"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        logging.error(f"Input directory {input_dir} does not exist")
        return
    
    # Find all PDF files
    pdf_files = list(input_path.glob("*.pdf"))
    if not pdf_files:
        logging.warning(f"No PDF files found in {input_dir}")
        return
    
    logging.info(f"Found {len(pdf_files)} PDF files to process")
    
    # Process each PDF
    successful = 0
    for pdf_file in pdf_files:
        output_file = output_path / f"{pdf_file.stem}.json"
        if process_single_pdf(pdf_file, output_file):
            successful += 1
    
    logging.info(f"Successfully processed {successful}/{len(pdf_files)} files")

def main():
    """Main entry point with enhanced argument handling"""
    parser = argparse.ArgumentParser(
        description="Extract document structure from PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.main document.pdf                    # Single file
  python -m app.main document.pdf -o outline.json    # Custom output
  python -m app.main --input-dir /data --output-dir /output  # Directory processing
        """
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("pdf", nargs="?", help="Single PDF file path")
    input_group.add_argument("--input-dir", help="Directory containing PDF files")
    
    # Output options
    parser.add_argument("-o", "--output", help="Output JSON file (for single PDF)")
    parser.add_argument("--output-dir", default="output", help="Output directory (default: output)")
    
    args = parser.parse_args()
    
    try:
        if args.pdf:
            # Single file processing
            pdf_path = Path(args.pdf)
            if not pdf_path.is_file():
                logging.error(f"PDF file not found: {args.pdf}")
                return 1
            
            # Determine output path
            if args.output:
                output_path = Path(args.output)
            else:
                output_path = Path(args.output_dir) / f"{pdf_path.stem}.json"
            
            success = process_single_pdf(pdf_path, output_path)
            return 0 if success else 1
            
        else:
            # Directory processing
            process_directory(args.input_dir, args.output_dir)
            return 0
            
    except KeyboardInterrupt:
        logging.info("Processing interrupted by user")
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())