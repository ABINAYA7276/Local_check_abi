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

def check_section_2(file_path):
    """
    Validate Section 2 (Security Requirement No & Name).
    Separates Section 2 from others using strict exclusion keywords.
    Aggregates content if split across sections.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 2", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        standard_title = "2. Security Requirement No & Name"
        stable_redirect = "Security Requirement No & Name"
        
        # 1. Identification (Silent Search)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            # Strict Search: Matches "2. " (with space) or titles containing 'security requirement'
            if title.startswith('2. ') or 'security requirement' in title_lower:
                target_section = section
                break
            if section.get('section_id') == 'SEC-02':
                target_section = section
                break

        if not target_section:
            return [{
                "where": standard_title,
                "what": "Section 2 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]

        # STRICT TITLE VALIDATION (BLOCKING)
        found_title = target_section.get('title', '').strip()
        # It MUST start with "2." and contain "Security Requirement No & Name" (case-insensitive)
        title_lower = found_title.lower()
        if not (found_title.startswith("2.") and "security requirement" in title_lower and "no & name" in title_lower):
             return [{
                "where": found_title if found_title else "Section 2",
                "what": "Section 2 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]

        actual_title = found_title
        import re
        # Clean redirect: Remove leading numbers/dots and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect

        errors = []
        has_valid_content = False
        found_text_sample = ""
        
        # Helper to check if text is valid (requires letters)
        def is_valid_content(t):
            t_clean = str(t).strip()
            if not t_clean: return False
            # Reject placeholders
            if t_clean.lower() in ['none', 'n/a', 'nil', '.', '-', '_', '...', '']:
                return False
            # Accept any other content
            return True

        # Check all possible content fields
        content_sources = []
        # Support both 'security_requirement' and 'content' fields
        sec_req = target_section.get('security_requirement', '')
        if sec_req: content_sources.append(sec_req)
        
        content = target_section.get('content', [])
        if isinstance(content, list): 
            for c_item in content:
                if isinstance(c_item, dict):
                    # Skip image types for validation (Consistent with other sections)
                    if c_item.get('type') == 'image' or c_item.get('image_path'):
                         continue
                    content_sources.append(c_item.get('text', ''))
                else:
                    content_sources.append(str(c_item))

        for text in content_sources:
            if isinstance(text, list): text = " ".join([str(i) for i in text if i])
            
            text = str(text).strip()
            if text:
                if not found_text_sample:
                    found_text_sample = text
                if is_valid_content(text):
                    has_valid_content = True
                    found_text_sample = text
                    break
        
        if not has_valid_content:
            errors.append({
                "where": actual_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the security requirement number and name details.",
                "redirect_text": redirect_val,
                "severity": "High"
            })
            
        return errors

    except Exception as e:
        return [{"where": "Section 2", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_2(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))
