#!/usr/bin/env python3
"""
Container entry point script that processes all PDFs in /app/input
and outputs JSON files to /app/output
"""

import os
import sys
import logging
from pathlib import Path

# Add app to Python path
sys.path.insert(0, '/app')

from app.main import process_directory

def main():
    """Process all PDFs in input directory"""
    input_dir = Path("/app/input")
    output_dir = Path("/app/output")
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    
    # Check if input directory exists and has PDFs
    if not input_dir.exists():
        logging.error("Input directory /app/input does not exist")
        return 1
    
    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        logging.warning("No PDF files found in /app/input")
        return 0
    
    logging.info(f"Container starting - found {len(pdf_files)} PDF files to process")
    
    # Ensure output directory exists
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Process all PDFs
    try:
        process_directory(str(input_dir), str(output_dir))
        logging.info("Container processing completed successfully")
        return 0
    except Exception as e:
        logging.error(f"Container processing failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())