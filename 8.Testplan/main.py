import json
import os
import re
import sys

def is_meaningful_content(t):
    if not t or not isinstance(t, str):
        return False
    t_clean = t.strip()
    if t_clean.lower() in ['none', 'n/a', 'nil', 'tbd', '...', '---', '', '.', '-']:
        return False
    return True

def check_section_8(file_path):
    """
    Validate Section 8 (Test Plan).
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 8 - Test Plan", "what": "File not found", "suggestion": "Provide a valid JSON file path", "severity": "high"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        all_errors_table = []
        target_section = None
        standard_title = "8. Test Plan"
        stable_redirect = "Test Plan"

        # 1. IDENTIFICATION (by static title body)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Identify by keywords "test" and "plan"
            if "test" in title_lower and "plan" in title_lower:
                # Exclude numerical subsections (e.g. 8.1, 8.2)
                # If there's a dot and content immediately after a number prefix that isn't just "8.", skip.
                if re.search(r'^\d+\.\d+', title):
                    continue
                target_section = section
                break

        if not target_section:
            return [{
                "where": standard_title,
                "what": "Section 8 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]

        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body
        has_body = "test" in title_lower and "plan" in title_lower

        # Identify any leading number prefix (handles 8., 8.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("8.")

        if not (has_correct_num and has_body):
            if has_body and has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = num_prefix_match.group(1).strip()
                all_errors_table.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '8.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '8.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_body and not has_any_number:
                # Title body is correct but section number "8." is missing entirely
                all_errors_table.append({
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
                    "what": "Section 8 missing",
                    "suggestion": f"Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "High"
                }]
            # proceed to content check if we have the body

        actual_title = found_title
        # Clean redirect: Remove leading numbers and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect
        
        # Content Check
        has_meaningful = False
        found_text_sample = ""
        
        # Check 'test_plan' first, then fallback to 'content'
        test_plan_data = target_section.get('test_plan', [])
        if not test_plan_data:
            test_plan_data = target_section.get('content', [])
        
        # Handle if it's a list or string
        check_list = test_plan_data if isinstance(test_plan_data, list) else ([test_plan_data] if test_plan_data else [])

        for item in check_list:
            text = ""
            if isinstance(item, dict):
                # Images NO LONGER count as content (Consistent with Section 5/7)
                text = item.get('text', '')
            elif isinstance(item, list):
                text = " ".join([str(i) for i in item if i])
            else:
                text = str(item)
                
            if is_meaningful_content(text):
                has_meaningful = True
                break
            elif text.strip() and not found_text_sample:
                 found_text_sample = text.strip()

        if not has_meaningful:
           all_errors_table.append({
               "where": actual_title, 
               "what": "Test Plan content is missing or non-descriptive", 
               "suggestion": "Add test plan introductory content", 
               "redirect_text": redirect_val,
               "severity": "high"
           })
        
        # Final Processing: Sort findings by severity: high > medium > low
        findings = []
        if all_errors_table:
            severity_priority = {"High": 0, "Medium": 1, "Low": 2}
            all_errors_table.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
            
            for error in all_errors_table:
                findings.append({
                    "where": error['where'],
                    "what": error['what'],
                    "suggestion": error['suggestion'],
                    "redirect_text": error.get('redirect_text', ''),
                    "severity": error.get('severity', 'Medium')
                })

        return findings if findings else None

    except Exception as e:
        return [{"where": "Section 8 Processing", "what": f"Error: {e}", "suggestion": "Check file structure", "severity": "high"}]

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8(json_path)
    
    # Always save to output.json
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result if result else [], f, indent=4)
    except:
        pass
        
    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1)
    else:
        sys.exit(0)
