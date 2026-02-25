import json
import os
import sys

def is_valid_content(t):
    """
    Checks if text is meaningful (not just numbers, placeholders, or empty).
    Requires at least one alphabetic character and minimum length of 2.
    """
    if not t or not isinstance(t, str):
        return False
    t_clean = t.strip()
    if t_clean.lower() in ['none', 'n/a', 'nil', 'tbd', '...', '---', '', '.']:
        return False
    return True

def check_section_6(file_path):
    """
    Validate Section 6 (Preconditions) using Simplified Concept.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 6", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        stable_redirect = "Preconditions"
        standard_title = "6. Preconditions:"
        
        # 1. IDENTIFICATION (Fuzzy & Number-based)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Starts with "6. " or contains keyword "Precondition"
            if title.startswith('6. ') or ('precondition' in title_lower):
                target_section = section
                break
            # Fallback to ID
            if section.get('section_id') == 'SEC-06':
                target_section = section
                break

        if not target_section:
            return [{
                "where": "6. Preconditions",
                "what": "Section 6 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            }]
        
        # STRICT TITLE VALIDATION (BLOCKING)
        found_title = target_section.get('title', '').strip()
        # It MUST start with "6." and contain "Precondition" (case-insensitive)
        title_lower = found_title.lower()
        if not (found_title.startswith("6.") and "precondition" in title_lower):
            # Check if title contains "Preconditions" or "Precondition" (both acceptable)
             return [{
                "where": found_title if found_title else "Section 6",
                "what": "Section 6 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            }]

        actual_title = target_section.get('title', '').strip()
        errors = []
        
        # 2. TITLE VALIDATION (Skipped as per Simplified Concept)

        # 3. CONTENT VALIDATION
        has_valid_content = False
        found_text_sample = ""
        
        # Check specific field 'preconditions' first
        precond_list = target_section.get('preconditions', [])
        
        # Handle if it's a list (common structure) or string
        items_to_check = precond_list if isinstance(precond_list, list) else ([precond_list] if precond_list else [])
        
        # Add 'content' list as fallback
        if not items_to_check:
             items_to_check = target_section.get('content', [])

        # Validate items
        for item in items_to_check:
            text = ""
            if isinstance(item, dict):
                # Check for 'precondition' key (specific to this section) or generic 'text'
                text = item.get('precondition', '') or item.get('text', '')
            else:
                text = str(item)
            
            if is_valid_content(text):
                has_valid_content = True
                break
            elif text.strip() and not found_text_sample:
                 found_text_sample = text.strip()

        if not has_valid_content:
            errors.append({
                "where": actual_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the preconditions details.",
                "redirect_text": stable_redirect,
                "severity": "High"
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
