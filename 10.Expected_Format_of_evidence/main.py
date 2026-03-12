import json
import os
import sys
import re

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
        found_title = ""
        
        # DEBUG
        # print(f"DEBUG: Processing {len(sections)} sections")

        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Robust Section Discovery Keywords
            has_10 = "10" in title_lower
            has_expected = "expected" in title_lower
            has_format = "format" in title_lower
            has_evidence = any(kw in title_lower for kw in ["evidence", "evid"])
            
            # Discovery logic:
            # Must have at least two of (expected, format, evidence) AND either have "10" OR have all three.
            match_count = sum([has_expected, has_format, has_evidence])
            if (match_count >= 3) or (has_10 and match_count >= 2):
                target_section = section
                found_title = title
                break
        
        if not target_section:
            return [{
                "where": expected_title,
                "what": "Section 10 missing",
                "suggestion": f"Add Section: '{expected_title}'",
                "redirect_text": expected_title,
                "severity": "high"
            }]
        
        # Determine redirect_title (without prefix) for UI redirection
        redirect_title = re.sub(r'^[\d\.]+\s*', '', found_title).strip() or found_title
        
        # TITLE VALIDATION
        title_lower = found_title.lower()
        # Robust prefix match: handles 10., 10.., etc.
        num_match = re.match(r'^([\d\.]+)', found_title)
        has_any_number = num_match is not None
        has_correct_num = found_title.startswith("10.")
        
        actual_prefix = num_match.group(1).strip() if num_match else "10"
        display_title = expected_title

        if not (has_correct_num and "expected format of evidence" in title_lower):
            if has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = actual_prefix
                findings.append({
                    "where": display_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '10.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '10.'. Expected: '{expected_title}'",
                    "redirect_text": redirect_title,
                    "severity": "Low"
                })
            elif not has_any_number:
                # Title body is correct but section number "10." is missing entirely
                findings.append({
                    "where": display_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{expected_title}'",
                    "redirect_text": redirect_title,
                    "severity": "Medium"
                })

            # Formatting / Space Checks
            if "expected format of evidence" not in title_lower:
                is_space_issue = any(part in title_lower for part in ["formatof", "ofevidence", "expectedformat", "10.."])
                what_msg = f"Incorrect formatting (space issue) in the title. Found: '{found_title}'" if is_space_issue else f"Incorrect formatting in the title. Found: '{found_title}'"
                
                findings.append({
                    "where": display_title,
                    "what": what_msg,
                    "suggestion": f"Fix the title to exactly match: '{expected_title}'",
                    "redirect_text": redirect_title,
                    "severity": "Low"
                })

        # Determine redirect_title for content checks (without prefix) -- THIS LINE IS REMOVED
        # redirect_title_for_content = re.sub(r'^[\d\.]+\s*', '', found_title).strip() or found_title -- THIS LINE IS REMOVED
        
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
                "where": display_title,
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
