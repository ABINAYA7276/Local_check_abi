import json
import os
import sys
import re

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
        expected_title = "8. Test Plan"

        # 1. Robust Section Discovery
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Match if contains "8" and "test"
            if "8" in title_lower and "test" in title_lower:
                # Strictly exclude subsections like 8.1, 8.2, 8.4, 81.1 etc.
                # If there's a digit immediately following the 8. (e.g. 8.1), it's a subsection.
                if re.search(r'^8\.\d+', title) or re.search(r'^\d+\.\d+(\.\d+)?', title):
                    # But if it's JUST "8." or "8. Test Plan", keep it.
                    # We check if the pattern is specifically a subsection pattern.
                    if re.match(r'^\d+\.\d+(\.\d+)?$', title.split(':')[0].strip()):
                         continue

                target_section = section
                break

        if not target_section:
            return [{
                "where": expected_title,
                "what": "Section 8 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": "Test Plan",
                "severity": "high"
            }]

        actual_title = target_section.get('title', '').strip()
        # Clean redirect title (remove leading numbers and trailing colons)
        redirect_title = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or "Test Plan"
        
        # Title Validation - STOP if wrong
        if actual_title.replace(':', '').strip().lower() != expected_title.replace(':', '').strip().lower():
             return [{
                "where": expected_title,
                "what": "Section 8 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": "Test Plan",
                "severity": "high"
            }]
        else:
            # Content Check
            has_meaningful = False
            found_text_sample = ""
            
            # Check 'test_plan' first, then fallback to 'content'
            items_to_check = target_section.get('test_plan', [])
            if not items_to_check:
                items_to_check = target_section.get('content', [])
            
            # Handle if it's a list or string
            check_list = items_to_check if isinstance(items_to_check, list) else ([items_to_check] if items_to_check else [])

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
                   "redirect_text": redirect_title,
                   "severity": "high"
               })
        
        # Final Processing: Sort findings by severity: high > medium > low
        findings = []
        if all_errors_table:
            severity_priority = {"high": 0, "medium": 1, "low": 2}
            all_errors_table.sort(key=lambda x: severity_priority.get(x.get('severity', 'medium'), 1))
            
            for error in all_errors_table:
                findings.append({
                    "where": error['where'],
                    "what": error['what'],
                    "suggestion": error['suggestion'],
                    "redirect_text": error.get('redirect_text', ''),
                    "severity": error.get('severity', 'medium')
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
