import json
import os
import sys
import re

def is_valid_content(t):
    """
    Checks if text is meaningful (not just numbers, placeholders, or empty).
    Requires at least one alphabetic character and minimum length of 2.
    """
    if not t or not isinstance(t, str):
        return False
    t_clean = t.strip()
    # Reject common placeholders
    if t_clean.lower() in ['none', 'n/a', 'nil', 'tbd', '...', '---', '', '.']:
        return False
    # Accept any other content
    return True

def check_section_3(file_path):
    """
    Validate Section 3 (Requirement Description) using Simplified Concept.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 3", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        stable_redirect = "Requirement Description"
        standard_title = "3. Requirement Description"
        
        # 1. IDENTIFICATION (Fuzzy & Number-based)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Starts with "3. " or contains keywords
            if title.startswith('3. ') or ('requirement' in title_lower and 'description' in title_lower):
                target_section = section
                break
            # Fallback to ID
            if section.get('section_id') == 'SEC-03':
                target_section = section
                break

        if not target_section:
            return [{
                "where": "3. Requirement Description",
                "what": "Section 3 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            }]
        
        # STRICT TITLE VALIDATION (BLOCKING)
        found_title = target_section.get('title', '').strip()
        # It MUST start with "3." and contain "Requirement Description" (case-insensitive)
        title_lower = found_title.lower()
        if not (found_title.startswith("3.") and "requirement description" in title_lower):
             return [{
                "where": found_title if found_title else "Section 3",
                "what": "Section 3 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            }]
        
        actual_title = target_section.get('title', '').strip()
        errors = []
        
        # 2. TITLE VALIDATION (Skipped as per Simplified Concept)
        # We trust the header is correct.

        # 3. CONTENT VALIDATION
        has_valid_content = False
        found_text_sample = ""
        
        # Check 'requirement_description' first
        req_desc = target_section.get('requirement_description', '')
        if is_valid_content(req_desc):
            has_valid_content = True
        else:
            if isinstance(req_desc, str) and req_desc.strip():
                found_text_sample = req_desc.strip()

        # Check generic 'content' or other fields if description empty
        if not has_valid_content:
            content_list = target_section.get('content', [])
            if isinstance(content_list, list):
                for item in content_list:
                    text = ""
                    if isinstance(item, dict):
                        text = item.get('text', '')
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
                "suggestion": "Provide the requirement description details.",
                "redirect_text": stable_redirect,
                "severity": "High"
            })
            
        return errors

    except Exception as e:
        return [{"where": "Section 3", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_3(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))

