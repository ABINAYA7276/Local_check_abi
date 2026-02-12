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

def check_section_3(file_path):
    """
    Validate Section 3 (Requirement Description).
    Separates Section 3 from others using strict exclusion keywords.
    Aggregates content if split across sections.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 3", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        expected_title = "3. Requirement Description"
        
        
        for section in sections:
            title = section.get('title', '').strip()
            
            # Strict Filtering:
            # 1. Starts with "3."
            # 2. NOT "3.1" (Subsections)
            # 3. Explicit ID 'SEC-03'
            
            if title.startswith('3.') and not title.startswith('3.1'):
                 candidates.append(section)
            elif section.get('section_id') == 'SEC-03':
                 candidates.append(section)

        if not candidates:
            return [{
                "where": "Section 3 - Requirement Description",
                "what": "Section 3 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]
        
        # 2. SELECT PRIMARY (For Title Check)
        primary_section = candidates[0]
        
        errors = []
        actual_title = primary_section.get('title', '').strip()
        
        # Normalize title for comparison
        clean_title = actual_title.rstrip(':').strip()
        
        if clean_title != expected_title:
             errors.append({
                "where": "Section 3 - Requirement Description",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })

        has_text = False
        found_invalid = ""
        
        # 3. Dynamic Content Aggregation
        for target in candidates:
            # Check 'requirement_description' key first
            req_desc = target.get('requirement_description', '')
            if isinstance(req_desc, str) and is_meaningful_content(req_desc):
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
            text_desc = f": Found '{found_invalid[:30]}...'" if found_invalid else ""
            errors.append({
                "where": "Section 3 - Requirement Description",
                "what": f"Requirement description content is missing{text_desc}",
                "suggestion": "Add a descriptive detail for the security requirement",
                "redirect_text": f"{actual_title}"
            })
        
        return errors

    except Exception as e:
        return [{"where": "Section 3", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_3(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    print(json.dumps(result if result else [], indent=4))
