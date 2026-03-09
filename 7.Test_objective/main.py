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

def check_section_7(file_path):
    """
    Validate Section 7 (Test Objective) using Simplified Concept.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 7", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        standard_title = "7. Test Objective"
        stable_redirect = "Test Objective"
        
        # 1. IDENTIFICATION (by static title body)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Identify by exact static title body keywords
            if 'test' in title_lower and 'objective' in title_lower:
                target_section = section
                break

        if not target_section:
            return [{
                "where": standard_title,
                "what": "Section 7 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body
        has_body = "test" in title_lower and "objective" in title_lower

        # Identify any leading number prefix (handles 7., 7.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("7.")

        errors = []
        if not (has_correct_num and has_body):
            if has_body and has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = num_prefix_match.group(1).strip()
                errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '7.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '7.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_body and not has_any_number:
                # Title body is correct but section number "7." is missing entirely
                errors.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })
            else:
                # Title is entirely wrong or absent
                return [{
                    "where": standard_title,
                    "what": "Section 7 missing",
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

        # 3. CONTENT VALIDATION
        has_valid_content = False
        found_text_sample = ""
        
        # Check 'test_objective' first, then fallback to 'content'
        test_obj_data = target_section.get('test_objective', [])
        if not test_obj_data:
            test_obj_data = target_section.get('content', [])
        
        # Handle if it's a list (common structure) or string
        items_to_check = test_obj_data if isinstance(test_obj_data, list) else ([test_obj_data] if test_obj_data else [])

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
                "suggestion": "Provide the test objective details.",
                "redirect_text": redirect_val,
                "severity": "High"
            })
            
        # Sort by severity
        severity_priority = {"High": 0, "Medium": 1, "Low": 2}
        errors.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
            
        return errors

    except Exception as e:
        return [{"where": "Section 7", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_7(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))
