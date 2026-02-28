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
        
        # 1. Check Title Correctness
        actual_title = target_section.get('title', '').strip()
        if actual_title.lower().replace(':', '') != expected_title.lower().replace(':', ''):
            findings.append({
                "where": expected_title,
                "what": f"Incorrect section title. Found: '{actual_title}'",
                "suggestion": f"Use exact title: '{expected_title}'",
                "redirect_text": actual_title,
                "severity": "medium"
            })
        
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
                "severity": "high"
            })
        
        return findings

    except Exception as e:
        return [{
            "where": "Section 10 Processing Error",
            "what": str(e),
            "suggestion": "Check JSON format",
            "redirect_text": "Error",
            "severity": "high"
        }]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_10(json_path)
    
    # Sort findings by severity: high > medium > low
    severity_priority = {"high": 0, "medium": 1, "low": 2}
    if isinstance(result, list):
        result.sort(key=lambda x: severity_priority.get(x.get('severity', 'medium'), 1))
    
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
