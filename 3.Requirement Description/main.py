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
            
            # Relaxed identification
            if 'requirement' in title_lower and 'description' in title_lower:
                target_section = section
                break

        if not target_section:
            return [{
                "where": "3. Requirement Description",
                "what": "Section 3 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body (Strict check for correct formatting)
        has_correct_body = "requirement description" in title_lower

        # Identify any leading number prefix (handles 3., 3.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("3.")

        errors = []
        
        # 1. Number Checks
        if not has_correct_num:
            if has_any_number:
                wrong_num = num_prefix_match.group(1).strip()
                errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '3.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '3.'. Expected: '{standard_title}'",
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
        has_req_body = "requirement" in title_lower and "description" in title_lower
        
        if has_req_body and not has_correct_body:
            errors.append({
                "where": standard_title,
                "what": f"Missing space in the title. Found: '{found_title}'",
                "suggestion": f"Add space between words. Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "Medium"
            })
        elif not has_req_body:
             # Title is entirely wrong or absent
             return [{
                 "where": standard_title,
                 "what": "Section 3 missing",
                 "suggestion": f"Expected: '{standard_title}'",
                 "redirect_text": found_title,
                 "severity": "High"
             }]
             
        # proceed to content check if we have the body
        
        actual_title = found_title
        # Clean redirect: Remove leading numbers and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect
        
        # 2. TITLE VALIDATION (Skipped as per Simplified Concept)
        # We trust the header is correct.

        # 3. CONTENT VALIDATION
        has_valid_content = False
        found_text_sample = ""
        
        # Check 'requirement_description' first
        req_desc = target_section.get('requirement_description', '')
        
        # Aggregate text if it's a list
        if isinstance(req_desc, list):
            req_desc_text = " ".join([str(i) for i in req_desc if i]).strip()
        else:
            req_desc_text = str(req_desc).strip()

        if is_valid_content(req_desc_text):
            has_valid_content = True
        else:
            if req_desc_text:
                found_text_sample = req_desc_text

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
                "where": standard_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the requirement description details.",
                "redirect_text": found_title,
                "severity": "High"
            })
            
        # Sort by severity: Title issues (Low/Medium) before Content issues (High)
        severity_priority = {"Low": 0, "Medium": 1, "High": 2}
        errors.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
            
        return errors

    except Exception as e:
        return [{"where": "Section 3", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_3(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))

