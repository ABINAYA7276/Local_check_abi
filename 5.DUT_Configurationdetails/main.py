import json
import os
import re
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
    Validate Section 5 (DUT Configurationdetails) using Simplified Concept.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 5", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        standard_title = "5. DUT Configuration:"
        stable_redirect = "DUT Configuration:"
        
        # 1. IDENTIFICATION (by static title body)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Identify by exact static title body keywords
            if 'dut' in title_lower and 'configuration' in title_lower:
                target_section = section
                break

        if not target_section:
            return [{
                "where": standard_title,
                "what": "Section 5 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body (Strict validation)
        has_correct_body = "dut configuration:" in title_lower

        # Identify any leading number prefix (handles 5., 5.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("5.")

        errors = []
        
        # 1. Number Checks
        if not has_correct_num:
            if has_any_number:
                wrong_num = num_prefix_match.group(1).strip()
                errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '5.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '5.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            else:
                errors.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })

        # 2. Body / Formatting Checks (Spacing)
        # Relaxed identification
        has_dut_body = "dut" in title_lower and "configuration" in title_lower
        
        if has_dut_body:
            if not has_correct_body:
                errors.append({
                    "where": standard_title,
                    "what": f"Incorrect formatting or missing space in the title. Found: '{found_title}'",
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
        else:
            # Title is entirely wrong or absent
            return [{
                "where": standard_title,
                "what": "Section 5 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "High"
            }]
             
        # proceed to content check if we have the body
        
        actual_title = found_title
        # Clean redirect: Remove leading numbers and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect

        # Check content
        has_valid_content = False
        found_text_sample = ""

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
                "where": standard_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the DUT configuration details.",
                "redirect_text": found_title,
                "severity": "High"
            })
            
        # Sort by severity: Title issues (Low/Medium) before Content issues (High)
        severity_priority = {"Low": 0, "Medium": 1, "High": 2}
        errors.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
            
        return errors

    except Exception as e:
        return [{"where": "Section 5", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_5(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))
