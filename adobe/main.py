import os
import re
import json
import pdfplumber
from collections import Counter
import unicodedata

INPUT_DIR = "app/input"
OUTPUT_DIR = "app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Multilingual noise patterns
MULTILINGUAL_NOISE_PATTERNS = {
    'universal': [
        r'copyright|©|®|™',
        r'page \d+|页\s*\d+|ページ\s*\d+|페이지\s*\d+|página\s*\d+|seite\s*\d+',
        r'version|संस्करण|版本|バージョン|버전|versión|version',
        r'www\.|http|\.com|\.org',
        r'[.\-_]{4,}',  # Dot leaders
        r'^\d{1,2}:\d{2}|^\d{1,2}/\d{1,2}/\d{2,4}',  # Times/dates
        r'^[^\w\s]*$',  # Only punctuation
    ],
    'english': [
        r'all rights reserved|confidential|internal use|draft',
        r'table of contents|index|appendix',
    ],
    'hindi': [
        r'सभी अधिकार सुरक्षित|गोपनीय|आंतरिक उपयोग|मसौदा',
        r'विषय सूची|अनुक्रमणिका|परिशिष्ट',
    ],
    'chinese': [
        r'版权所有|保密|内部使用|草稿',
        r'目录|索引|附录',
    ],
    'japanese': [
        r'著作権|機密|内部使用|下書き',
        r'目次|索引|付録',
    ],
    'korean': [
        r'저작권|기밀|내부 사용|초안',
        r'목차|색인|부록',
    ],
    'spanish': [
        r'derechos reservados|confidencial|uso interno|borrador',
        r'índice|tabla de contenidos|apéndice',
    ],
    'french': [
        r'droits réservés|confidentiel|usage interne|brouillon',
        r'table des matières|index|annexe',
    ],
    'german': [
        r'alle rechte vorbehalten|vertraulich|interne verwendung|entwurf',
        r'inhaltsverzeichnis|index|anhang',
    ]
}

# Multilingual heading indicators
MULTILINGUAL_HEADING_PATTERNS = {
    'numbered_sections': [
        r'^\d+(\.\d+)*\.?\s+',  # Universal numbering
        r'^第\d+章|^第\d+节',  # Chinese chapters/sections
        r'^第\d+章|^第\d+節',  # Traditional Chinese
        r'^\d+장|^\d+절',      # Korean chapters/sections
        r'^第\d+章',           # Japanese chapters
        r'^अध्याय\s*\d+|^खंड\s*\d+',  # Hindi chapters/sections
        r'^capítulo\s*\d+|^sección\s*\d+',  # Spanish
        r'^chapitre\s*\d+|^section\s*\d+',  # French
        r'^kapitel\s*\d+|^abschnitt\s*\d+', # German
    ],
    'appendix_patterns': [
        r'^appendix\s+[a-z]',     # English
        r'^anexo\s+[a-z]',        # Spanish
        r'^annexe\s+[a-z]',       # French
        r'^anhang\s+[a-z]',       # German
        r'^परिशिष्ट\s*[a-z]',      # Hindi
        r'^附录\s*[a-z]',          # Chinese
        r'^付録\s*[a-z]',          # Japanese
        r'^부록\s*[a-z]',          # Korean
    ]
}

# Common instruction words in different languages
INSTRUCTION_WORDS = {
    'english': ['required', 'please', 'visit', 'fill', 'complete', 'enter', 'select'],
    'hindi': ['आवश्यक', 'कृपया', 'भरें', 'पूरा', 'दर्ज', 'चुनें'],
    'chinese': ['必需', '请', '填写', '完成', '输入', '选择'],
    'japanese': ['必要', 'してください', '記入', '完了', '入力', '選択'],
    'korean': ['필수', '제발', '채우다', '완료', '입력', '선택'],
    'spanish': ['requerido', 'por favor', 'llenar', 'completar', 'entrar', 'seleccionar'],
    'french': ['requis', 's\'il vous plaît', 'remplir', 'compléter', 'entrer', 'sélectionner'],
    'german': ['erforderlich', 'bitte', 'ausfüllen', 'vervollständigen', 'eingeben', 'auswählen']
}

def detect_script_type(text):
    """Detect the primary script/language family of text"""
    if not text:
        return 'latin'
    
    scripts = {
        'chinese': 0,
        'japanese': 0,
        'korean': 0,
        'devanagari': 0,  # Hindi
        'latin': 0,
        'cyrillic': 0
    }
    
    for char in text:
        if '\u4e00' <= char <= '\u9fff':  # CJK Unified Ideographs
            scripts['chinese'] += 1
        elif '\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff':  # Hiragana/Katakana
            scripts['japanese'] += 1
        elif '\uac00' <= char <= '\ud7af':  # Hangul
            scripts['korean'] += 1
        elif '\u0900' <= char <= '\u097f':  # Devanagari
            scripts['devanagari'] += 1
        elif '\u0400' <= char <= '\u04ff':  # Cyrillic
            scripts['cyrillic'] += 1
        elif char.isalpha():
            scripts['latin'] += 1
    
    return max(scripts, key=scripts.get)

def is_multilingual_noise(line, repeated_lines, line_context):
    """Enhanced multilingual noise detection"""
    line_lower = line.lower().strip()
    
    # Skip if repeated across pages (headers/footers)
    if line.strip() in repeated_lines:
        return True
    
    # Basic noise patterns
    if not line_lower or len(line_lower) < 2:
        return True
    
    # Check against all multilingual noise patterns
    for lang_patterns in MULTILINGUAL_NOISE_PATTERNS.values():
        for pattern in lang_patterns:
            if re.search(pattern, line_lower, re.IGNORECASE):
                return True
    
    # Skip if part of address/form block
    if line_context.get('short_lines_nearby', 0) >= 4:
        return True
    
    # Skip pure numbers or symbols
    if re.match(r'^[\d\s\-_.()]+$', line.strip()):
        return True
    
    return False

def is_multilingual_heading_candidate(line, context, doc_stats):
    """Enhanced multilingual heading detection"""
    words = line.split()
    line_clean = line.strip()
    script_type = detect_script_type(line)
    
    # Adjust length constraints based on script
    if script_type in ['chinese', 'japanese']:
        max_chars = 50  # CJK characters are denser
        max_words = 20
    else:
        max_chars = 120
        max_words = 15
    
    # Length constraints
    if len(words) > max_words or len(line) > max_chars:
        return False
    
    # Skip if surrounded by many short lines (forms/addresses)
    if context.get('short_lines_nearby', 0) >= 4:
        return False
    
    # Strong positive signals
    
    # 1. Numbered sections (universal)
    for pattern in MULTILINGUAL_HEADING_PATTERNS['numbered_sections']:
        if re.match(pattern, line, re.IGNORECASE):
            return True
    
    # 2. Appendix patterns (multilingual)
    for pattern in MULTILINGUAL_HEADING_PATTERNS['appendix_patterns']:
        if re.match(pattern, line, re.IGNORECASE):
            return True
    
    # 3. All caps headings (but exclude instructions)
    if line.isupper() and 2 <= len(words) <= 8:
        # Check against instruction words in all languages
        is_instruction = False
        for lang_words in INSTRUCTION_WORDS.values():
            if any(word.lower() in line.lower() for word in lang_words):
                is_instruction = True
                break
        
        if not is_instruction:
            # Exclude address patterns (more universal)
            if not re.match(r'^\d+\s+[A-Z\s]+$|^[A-Z\s]+,\s*[A-Z]{2}', line):
                return True
    
    # 4. Title case headings (mainly for Latin scripts)
    if script_type == 'latin' and line.istitle() and 3 <= len(words) <= 10:
        if not line.endswith(':'):
            return True
    
    # 5. High uppercase ratio (for Latin scripts)
    if script_type == 'latin':
        uppercase_ratio = sum(c.isupper() for c in line) / max(1, len(line))
        if 0.6 <= uppercase_ratio < 1.0 and len(words) <= 10:
            return True
    
    # 6. Colon-ended section headers (universal)
    if line.endswith(':') and 2 <= len(words) <= 8:
        return True
    
    # 7. CJK specific patterns
    if script_type in ['chinese', 'japanese']:
        # Check for common CJK section markers
        if re.search(r'[一二三四五六七八九十]、|[①②③④⑤⑥⑦⑧⑨⑩]', line):
            return True
        # Bold or emphasized text patterns
        if len(line) <= 30 and not line.endswith('。'):  # Not ending with period
            return True
    
    # 8. Korean specific patterns
    if script_type == 'korean':
        # Korean section markers
        if re.search(r'[가나다라마바사아자차카타파하]\.', line):
            return True
    
    # 9. Hindi/Devanagari specific patterns
    if script_type == 'devanagari':
        # Hindi numbering and section markers
        if re.search(r'[१२३४५६७८९०]|अध्याय|भाग|खंड', line):
            return True
    
    return False

def get_multilingual_heading_level(text):
    """Determine heading level with multilingual support"""
    text = text.strip()
    script_type = detect_script_type(text)
    
    # Multi-level numbering (universal)
    if re.match(r'^\d+(\.\d+){3,}', text):
        return "H4"
    elif re.match(r'^\d+(\.\d+){2}', text):
        return "H3"
    elif re.match(r'^\d+\.\d+', text):
        return "H2"
    elif re.match(r'^\d+\.?\s', text):
        return "H1"
    
    # Chinese/Japanese chapter patterns
    elif re.match(r'^第\d+章', text):
        return "H1"
    elif re.match(r'^第\d+节|^第\d+節', text):
        return "H2"
    
    # Korean patterns
    elif re.match(r'^\d+장', text):
        return "H1"
    elif re.match(r'^\d+절', text):
        return "H2"
    
    # Hindi patterns
    elif re.match(r'^अध्याय\s*\d+', text):
        return "H1"
    elif re.match(r'^खंड\s*\d+|^भाग\s*\d+', text):
        return "H2"
    
    # Appendix patterns (multilingual)
    elif any(re.match(pattern, text, re.IGNORECASE) 
             for pattern in MULTILINGUAL_HEADING_PATTERNS['appendix_patterns']):
        return "H2"
    
    # Colon-ended headers
    elif text.endswith(':') and len(text.split()) <= 5:
        return "H3"
    
    # CJK specific levels
    elif script_type in ['chinese', 'japanese']:
        if re.search(r'[一二三四五六七八九十]、', text):
            return "H2"
        elif re.search(r'[①②③④⑤⑥⑦⑧⑨⑩]', text):
            return "H3"
    
    return "H1"

def clean_multilingual_heading(text):
    """Clean heading text with multilingual support"""
    text = text.strip()
    
    # Remove trailing dots and page numbers (universal)
    text = re.sub(r'[.\-_]{3,}$', '', text)
    text = re.sub(r'\s+\d+$', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    
    # Remove common trailing punctuation
    text = re.sub(r'[.。．]{1,2}$', '', text)
    
    # Normalize Unicode (important for multilingual text)
    text = unicodedata.normalize('NFKC', text)
    
    return text.strip()

def extract_multilingual_title(first_page_lines, repeated_lines):
    """Extract document title with multilingual support"""
    for line in first_page_lines[:10]:  # Check more lines for multilingual docs
        line_clean = line.strip()
        script_type = detect_script_type(line_clean)
        
        # Adjust constraints based on script
        if script_type in ['chinese', 'japanese']:
            min_len, max_len, max_words = 3, 80, 25
        else:
            min_len, max_len, max_words = 5, 100, 15
        
        if (min_len < len(line_clean) < max_len and 
            line_clean not in repeated_lines and
            len(line_clean.split()) <= max_words and
            not is_multilingual_noise(line_clean, repeated_lines, {})):
            return clean_multilingual_heading(line_clean)
    return ""

def extract_outline(pdf_path):
    """Main extraction function with multilingual support"""
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []
        page_texts = []
        
        # Collect all text
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            page_texts.append(lines)
            all_lines.extend(lines)
        
        if not all_lines:
            return {"title": "", "outline": []}
        
        # Calculate document statistics
        doc_stats = {
            'total_lines': len(all_lines),
            'avg_line_length': sum(len(line.split()) for line in all_lines) / len(all_lines),
            'primary_script': detect_script_type(' '.join(all_lines[:50]))  # Detect from first 50 lines
        }
        
        # Find repeated lines (headers/footers)
        line_counts = Counter(all_lines)
        repeated_threshold = max(2, len(pdf.pages) // 3)
        repeated_lines = {line for line, count in line_counts.items() 
                         if count >= repeated_threshold}
        
        # Extract title
        title = extract_multilingual_title(page_texts[0] if page_texts else [], repeated_lines)
        
        # For documents with very few unique lines, likely forms
        unique_ratio = len(set(all_lines)) / len(all_lines)
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
                if is_multilingual_noise(line, repeated_lines, context):
                    continue
                
                # Check if it's a heading candidate
                if is_multilingual_heading_candidate(line, context, doc_stats):
                    clean_text = clean_multilingual_heading(line)
                    
                    # Skip duplicates and title
                    if (clean_text and 
                        clean_text.lower() != title.lower() and 
                        clean_text.lower() not in seen_headings):
                        
                        level = get_multilingual_heading_level(clean_text)
                        
                        outline.append({
                            "level": level,
                            "text": clean_text,
                            "page": page_idx,  # Zero-based indexing
                            "script_type": detect_script_type(clean_text)
                        })
                        
                        seen_headings.add(clean_text.lower())
        
        return {
            "title": title, 
            "outline": outline,
            "document_script": doc_stats['primary_script']
        }

def analyze_line_context(lines, current_idx):
    """Analyze context around current line (unchanged)"""
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

# Process all PDFs
if __name__ == "__main__":
    print("🌐 Multilingual PDF Outline Extractor")
    print("Supports: English, Hindi, Chinese, Japanese, Korean, Spanish, French, German")
    print("-" * 70)
    
    processed_count = 0
    for filename in os.listdir(INPUT_DIR):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(INPUT_DIR, filename)
            try:
                result = extract_outline(pdf_path)
                output_path = os.path.join(OUTPUT_DIR, filename.replace('.pdf', '.json'))
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                script_info = f"({result.get('document_script', 'unknown')} script)"
                outline_count = len(result.get('outline', []))
                print(f"✅ {filename} {script_info} - {outline_count} headings extracted")
                processed_count += 1
                
            except Exception as e:
                print(f"❌ Error processing {filename}: {str(e)}")
    
    print(f"\n🎉 Processing complete! {processed_count} files processed.")
