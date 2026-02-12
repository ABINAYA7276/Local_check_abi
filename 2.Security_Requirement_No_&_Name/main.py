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
        candidates = []
        expected_title = "2. Security Requirement No & Name"
        
        # 1. Strictly identify Section 2
        
        for section in sections:
            title = section.get('title', '').strip()
            sec_id = section.get('section_id', '')
            
            # Strict logic: 
            # 1. Explicit ID matches
            if sec_id == 'SEC-02':
                 candidates.append(section)
                 continue
            
            # 2. Starts with '2.' (excluding '2.1') 
            # AND strictly ensure it's not another known section ID mislabeled
            if title.startswith('2.') and not title.startswith('2.1'):
                 if sec_id not in ['SEC-01', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11', 'SEC-12']:
                     candidates.append(section)
        
        if not candidates:
            return [{
                "where": "Section 2 - Security Requirement No & Name",
                "what": "Section 2 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]
        
        # 2. SELECT PRIMARY (For Title Check)
        primary_section = candidates[0] # Taking first match as primary

        errors = []
        actual_title = primary_section.get('title', '').strip()
        
        # Normalize title for comparison (remove trailing colon if present)
        clean_title = actual_title.rstrip(':').strip()
        
        if clean_title != expected_title:
             errors.append({
                "where": "Section 2 - Security Requirement No & Name",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": re.sub(r'^[\d\.]+\s*', '', actual_title).strip()
            })
        
        has_text = False
        found_invalid = ""
        
        # 3. Dynamic Content Aggregation
        for target in candidates:
            # Check 'security_requirement' key first (from structured extraction)
            sec_req = target.get('security_requirement', '')
            if isinstance(sec_req, str) and is_meaningful_content(sec_req):
                has_text = True
                break
            
            # Check generic content
            content = target.get('content', [])
            if isinstance(content, list):
                 for item in content:
                    text = item.get('text', '') if isinstance(item, dict) else str(item)
                    if is_meaningful_content(text):
                        has_text = True
                        break
                    elif text.strip() and not found_invalid:
                        found_invalid = text.strip()
            
            if has_text: break

        if not has_text:
            text_desc = f": Found '{found_invalid}'" if found_invalid else ""
            errors.append({
                "where": "Section 2 - Security Requirement No & Name",
                "what": f"Security requirement content is missing{text_desc}",
                "suggestion": "Add specific security requirement name (e.g., Access and Authorization)",
                "redirect_text": f"{actual_title}"
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
