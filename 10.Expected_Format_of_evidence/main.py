import json
import os
import sys

def check_section_10(file_path):
    """
    Validates Section 10: Expected Format of Evidence.
    Checks for: 
    1. Section existence (Robust discovery via keywords).
    2. Title correctness.
    3. Content presence.
    Returns findings in fixed JSON format.
    """
    findings = []
    expected_title = "10. Expected Format of Evidence:"
    
    if not os.path.exists(file_path):
        return [{
            "where": "File Status",
            "what": "File not found",
            "suggestion": f"Ensure file '{file_path}' exists",
            "redirect_text": "File missing",
            "severity": "high"
        }]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Robust Section Discovery Keywords
            # We check if the keyword or its common abbreviation is in the title
            discovery_keywords = [
                ("10",), 
                ("expected",), 
                ("format",), 
                ("of",), 
                ("evidence", "evid")
            ]
            
            if all(any(variant in title_lower for variant in kw_tuple) for kw_tuple in discovery_keywords):
                target_section = section
                break
        
        if not target_section:
            return [{
                "where": expected_title,
                "what": "Section 10 missing",
                "suggestion": f"Add Section: '{expected_title}'",
                "redirect_text": expected_title,
                "severity": "high"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body
        has_body = "expected" in title_lower and "format" in title_lower and "evidence" in title_lower

        # Identify any leading number prefix (handles 10., 10.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("10.")

        if not (has_correct_num and has_body):
            if has_body and has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = num_prefix_match.group(1).strip()
                findings.append({
                    "where": expected_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '10.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '10.'. Expected: '{expected_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_body and not has_any_number:
                # Title body is correct but section number "10." is missing entirely
                findings.append({
                    "where": expected_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{expected_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })
            else:
                # Title is entirely wrong or absent
                return [{
                    "where": expected_title,
                    "what": "Section 10 missing",
                    "suggestion": f"Expected: '{expected_title}'",
                    "redirect_text": found_title,
                    "severity": "High"
                }]
            # proceed to content check if we have the body

        actual_title = found_title
        
        import re
        redirect_title = re.sub(r'^[\d\.]+\s*', '', actual_title).strip() or actual_title
        
        has_text = False
        if not has_text:
            # Check 'expected_format_of_evidence' first, then fallback to 'content'
            items_to_check = []
            exp_fmt = target_section.get('expected_format_of_evidence', [])
            if exp_fmt:
                if isinstance(exp_fmt, list): items_to_check.extend(exp_fmt)
                else: items_to_check.append(exp_fmt)
            
            # Fallback to content
            if not items_to_check:
                items_to_check = target_section.get('content', [])

            # Handle if it's a list or string
            check_list = items_to_check if isinstance(items_to_check, list) else ([items_to_check] if items_to_check else [])

            found_text_sample = ""
            for item in check_list:
                text = ""
                if isinstance(item, dict):
                    # Count images as valid content
                    if item.get('type') == 'image' or item.get('image_path'):
                        has_text = True
                        break
                    text = item.get('text', '').strip()
                elif isinstance(item, list):
                    text = " ".join([str(i) for i in item if i]).strip()
                else:
                    text = str(item).strip()
                
                if text:
                    text_lower = text.lower()
                    if (text_lower not in ['none', 'n/a', 'nil', '.', '-', '_', '...'] and
                        len(text) > 2 and
                        not all(c in '.-_,;:!? ' for c in text)):
                        has_text = True
                        break
                    elif not found_text_sample:
                        found_text_sample = text
        
        if not has_text:
            # Capture the first thing we found to show in the error message
            found_val = found_text_sample if found_text_sample else "None"
            findings.append({
                "where": expected_title,
                "what": f"content missing in {expected_title}. Found: '{found_val}'",
                "suggestion": "Add Expected Format of Evidence description",
                "redirect_text": redirect_title,
                "severity": "High"
            })
        
        return findings

    except Exception as e:
        return [{
            "where": "Section 10 Processing Error",
            "what": str(e),
            "suggestion": "Check JSON format",
            "redirect_text": "Error",
            "severity": "High"
        }]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_10(json_path)
    
    # Sort findings by severity: High > Medium > Low
    severity_priority = {"High": 0, "Medium": 1, "Low": 2}
    if isinstance(result, list):
        result.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
    
    # Save to output.json (silent)
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result if result else [], f, indent=4)
    except Exception:
        pass
    
    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1)
    else:
        sys.exit(0)
