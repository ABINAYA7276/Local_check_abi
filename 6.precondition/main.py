import json
import os
import sys
import re

def is_meaningful_content(text):
    if not text or not isinstance(text, str): return False
    val = text.strip().lower()
    if val in ['none', 'n/a', 'nil', '.', '-', '...', '_']: return False
    words = re.findall(r'[A-Za-z0-9]+', text)
    return len(words) >= 2

def check_section_6(file_path):
    """
    Validate Section 6 (Preconditions).
    Standardized: Strict Exclusion, Dynamic Aggregation, Title Check.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 6", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        expected_title = "6. Preconditions"
        
        
        # 1. Strictly identify Section 6
        
        for section in sections:
            title = section.get('title', '').strip()
            sec_id = section.get('section_id', '')
            
            # Explicit Exclusion of other sections
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11', 'SEC-12']:
                continue

            # Strict logic: 
            # 1. Explicit ID matches
            if sec_id == 'SEC-06':
                 candidates.append(section)
                 continue
            
            # 2. Starts with '6.' (excluding '6.1') 
            if title.startswith('6.') and not title.startswith('6.1'):
                 candidates.append(section)
        
        if not candidates:
            return [{
                "where": "Section 6 - Preconditions",
                "what": "Section 6 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]
        
        # 2. SELECT PRIMARY
        primary_section = None
        for cand in candidates:
            if cand.get('section_id') == 'SEC-06':
                primary_section = cand
                break
        if not primary_section:
            primary_section = candidates[0]

        errors = []
        actual_title = primary_section.get('title', '').strip()
        
        # Normalization: Remove trailing colon for comparison
        norm_actual = actual_title.rstrip(':').strip()
        norm_expected = expected_title.rstrip(':').strip()
        
        if norm_actual != norm_expected:
             errors.append({
                "where": "Section 6 - Preconditions",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })

        has_text = False
        found_invalid = ""
        
        # 3. Dynamic Aggregation
        for target in candidates:
            # Check 'preconditions' list (objects or strings) and 'content' list
            field_sources = [target.get('preconditions', []), target.get('content', [])]
            
            for field in field_sources:
                items = field if isinstance(field, list) else [field]
                for item in items:
                    text = ""
                    if isinstance(item, dict):
                         # Logic for handling Precondition Objects specifically
                         text = item.get('precondition', '') or item.get('text', '')
                    else:
                        text = str(item)
                    
                    if is_meaningful_content(text):
                        has_text = True
                        break
                    elif text.strip() and not found_invalid:
                        found_invalid = text.strip()
                if has_text: break
            if has_text: break

        if not has_text:
            errors.append({
                "where": "Section 6 - Preconditions",
                "what": "Preconditions content is missing or non-descriptive",
                "suggestion": "Add meaningful test preconditions",
                "redirect_text": f"{actual_title}"
            })
        
        return errors

    except Exception as e:
        return [{"where": "Section 6", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_6(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))
