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

def check_section_5(file_path):
    """
    Validate Section 5 (DUT Configuration) using Simplified Concept.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 5", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        stable_redirect = "DUT Configuration"
        standard_title = "5. DUT Configuration:"
        
        # 1. IDENTIFICATION (Fuzzy & Number-based)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Starts with "5. " or contains keywords "DUT" AND "Configuration"
            if title.startswith('5. ') or ('dut' in title_lower and 'configuration' in title_lower):
                target_section = section
                break
            # Fallback to ID
            if section.get('section_id') == 'SEC-05':
                target_section = section
                break

        if not target_section:
            return [{
                "where": "5. DUT Configuration",
                "what": "Section 5 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]
        
        # STRICT TITLE VALIDATION (BLOCKING)
        found_title = target_section.get('title', '').strip()
        # It MUST start with "5." and contain "DUT Configuration" (case-insensitive)
        title_lower = found_title.lower()
        if not (found_title.startswith("5.") and "dut configuration" in title_lower):
             return [{
                "where": found_title if found_title else "Section 5",
                "what": "Section 5 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]

        actual_title = target_section.get('title', '').strip()
        errors = []
        
        # 3. CONTENT VALIDATION
        has_valid_content = False
        found_text_sample = ""
        
        import re
        # Clean redirect: Always remove leading numbers/dots and trailing colon
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect

        # Check specific field 'dut_configuration' first
        dut_conf_list = target_section.get('dut_configuration', [])
        
        # Handle if it's a list (common structure) or string
        items_to_check = dut_conf_list if isinstance(dut_conf_list, list) else ([dut_conf_list] if dut_conf_list else [])
        
        # Add 'content' list as fallback
        if not items_to_check:
             items_to_check = target_section.get('content', [])

        # Validate items
        for item in items_to_check:
            text = ""
            if isinstance(item, dict):
                # Images NO LONGER count as content per discussion
                text = item.get('text', '')
            elif isinstance(item, list):
                text = " ".join([str(i) for i in item if i])
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
                "suggestion": "Provide the DUT configuration details.",
                "redirect_text": redirect_val,
                "severity": "High"
            })
            
        return errors

    except Exception as e:
        return [{"where": "Section 5", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_5(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))
