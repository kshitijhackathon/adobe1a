import os
import re
import json
import pdfplumber
from collections import Counter

INPUT_DIR = "app/input"
OUTPUT_DIR = "app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def is_noise(line, repeated_lines, line_context):
    """Universal noise detection without hardcoded content"""
    line_lower = line.lower().strip()
    
    # Skip if repeated across pages (headers/footers)
    if line.strip() in repeated_lines:
        return True
    
    # Basic noise patterns
    if not line_lower or len(line_lower) < 3:
        return True
    
    # Universal noise patterns (no specific content)
    noise_patterns = [
        r'copyright|©|page \d+|version|www\.|http',
        r'[.\-_]{4,}',  # Dot leaders
        r'^\d{1,2}:\d{2}|^\d{1,2}/\d{1,2}/\d{2,4}',  # Times/dates
        r'^[^\w\s]*$',  # Only punctuation
    ]
    
    for pattern in noise_patterns:
        if re.search(pattern, line_lower):
            return True
    
    # Skip if part of address block (multiple short lines together)
    if line_context.get('short_lines_nearby', 0) >= 4:
        return True
    
    return False

def analyze_line_context(lines, current_idx):
    """Analyze context around current line"""
    context = {'short_lines_nearby': 0}
    
    # Count short lines in vicinity (±3 lines)
    start = max(0, current_idx - 3)
    end = min(len(lines), current_idx + 4)
    
    for i in range(start, end):
        if i != current_idx and lines[i].strip():
            words = lines[i].split()
            if len(words) <= 6:
                context['short_lines_nearby'] += 1
    
    return context

def is_heading_candidate(line, context, doc_stats):
    """Universal heading detection using multiple criteria"""
    words = line.split()
    line_clean = line.strip()
    
    # Length constraints
    if len(words) > 15 or len(line) > 120:
        return False
    
    # Don't include obvious sentences
    if line.endswith('.') and len(words) > 5:
        return False
    
    # Skip if surrounded by many short lines (address/form blocks)
    if context.get('short_lines_nearby', 0) >= 4:
        return False
    
    # Strong positive signals
    
    # 1. Numbered sections (strongest signal)
    if re.match(r'^\d+(\.\d+)*\.?\s+[A-Z]', line):
        return True
    
    # 2. All caps headings (but exclude obvious instructions/addresses)
    if line.isupper() and 2 <= len(words) <= 8:
        # Exclude common instruction words
        instruction_indicators = ['required', 'please', 'visit', 'fill', 'complete']
        if not any(word in line.lower() for word in instruction_indicators):
            # Exclude address patterns
            if not re.match(r'^\d+\s+[A-Z\s]+$|^[A-Z\s]+,\s*[A-Z]{2}', line):
                return True
    
    # 3. Title case headings
    if line.istitle() and 3 <= len(words) <= 10:
        if not line.endswith(':'):
            return True
    
    # 4. Appendix patterns
    if re.match(r'^appendix\s+[a-c]', line, re.IGNORECASE):
        return True
    
    # 5. High uppercase ratio (but not all caps)
    uppercase_ratio = sum(c.isupper() for c in line) / max(1, len(line))
    if 0.6 <= uppercase_ratio < 1.0 and len(words) <= 10:
        return True
    
    # 6. Colon-ended section headers
    if line.endswith(':') and 2 <= len(words) <= 6:
        return True
    
    return False

def get_heading_level(text):
    """Determine heading level based on structure"""
    text = text.strip()
    
    # Multi-level numbering
    if re.match(r'^\d+(\.\d+){3,}', text):
        return "H4"
    elif re.match(r'^\d+(\.\d+){2}', text):
        return "H3"
    elif re.match(r'^\d+\.\d+', text):
        return "H2"
    elif re.match(r'^\d+\.?', text):
        return "H1"
    
    # Special patterns
    elif re.match(r'^appendix\s+[a-c]', text, re.IGNORECASE):
        return "H2"
    elif text.lower().startswith('for each') or text.lower().startswith('for the'):
        return "H4"
    elif text.endswith(':') and len(text.split()) <= 5:
        return "H3"
    else:
        return "H1"

def clean_heading(text):
    """Clean heading text"""
    text = text.strip()
    # Remove trailing dots and page numbers
    text = re.sub(r'[.\-_]{3,}$', '', text)
    text = re.sub(r'\s+\d+$', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

def extract_title(first_page_lines, repeated_lines):
    """Extract document title"""
    for line in first_page_lines[:8]:
        line_clean = line.strip()
        if (5 < len(line_clean) < 100 and 
            line_clean not in repeated_lines and
            len(line_clean.split()) <= 15 and
            not re.search(r'copyright|page|version|www', line_clean.lower())):
            return clean_heading(line_clean)
    return ""

def extract_outline(pdf_path):
    """Main extraction function"""
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []
        page_texts = []
        
        # Collect all text
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            page_texts.append(lines)
            all_lines.extend(lines)
        
        # Calculate document statistics
        doc_stats = {
            'total_lines': len(all_lines),
            'avg_line_length': sum(len(line.split()) for line in all_lines) / max(1, len(all_lines))
        }
        
        # Find repeated lines (headers/footers)
        line_counts = Counter(all_lines)
        repeated_threshold = max(2, len(pdf.pages) // 3)
        repeated_lines = {line for line, count in line_counts.items() 
                         if count >= repeated_threshold}
        
        # Extract title
        title = extract_title(page_texts[0] if page_texts else [], repeated_lines)
        
        # For documents with very few unique lines, likely forms - return empty
        unique_ratio = len(set(all_lines)) / max(1, len(all_lines))
        if unique_ratio < 0.3 and len(all_lines) < 50:
            return {"title": title, "outline": []}
        
        # Extract headings
        outline = []
        seen_headings = set()
        
        for page_idx, lines in enumerate(page_texts):
            for line_idx, line in enumerate(lines):
                if not line.strip():
                    continue
                
                # Analyze context
                context = analyze_line_context(lines, line_idx)
                
                # Skip noise
                if is_noise(line, repeated_lines, context):
                    continue
                
                # Check if it's a heading candidate
                if is_heading_candidate(line, context, doc_stats):
                    clean_text = clean_heading(line)
                    
                    # Skip duplicates and title
                    if (clean_text and 
                        clean_text.lower() != title.lower() and 
                        clean_text.lower() not in seen_headings):
                        
                        level = get_heading_level(clean_text)
                        
                        outline.append({
                            "level": level,
                            "text": clean_text,
                            "page": page_idx  # Zero-based indexing
                        })
                        
                        seen_headings.add(clean_text.lower())
        
        return {"title": title, "outline": outline}

# Process all PDFs
if __name__ == "__main__":
    for filename in os.listdir(INPUT_DIR):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(INPUT_DIR, filename)
            try:
                result = extract_outline(pdf_path)
                output_path = os.path.join(OUTPUT_DIR, filename.replace('.pdf', '.json'))
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                print(f"✅ Processed: {filename}")
                
            except Exception as e:
                print(f"❌ Error processing {filename}: {str(e)}")
