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

def check_section_7(file_path):
    """
    Validate Section 7 (Test Objective).
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 7", "what": "File not found", "suggestion": "Provide a valid JSON file path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        errors = []
        target_sections = []
        expected_title = "7. Test Objective"

        for section in sections:
            title = section.get('title', '').strip()
            sec_id = section.get('section_id', '')
            
            # HARD GUARD: Never process other known sections
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11', 'SEC-12']:
                continue

            # Strict logic: 
            # 1. Explicit ID matches
            if sec_id == 'SEC-07':
                 target_sections.append(section)
                 continue
            
            # 2. Starts with '7.' (excluding '7.1') 
            if title.startswith('7.') and not title.startswith('7.1'):
                 target_sections.append(section)

        if not target_sections:
            return [{
                "where": "Section 7 - Test Objective",
                "what": "Section 7 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]

        # Use the first valid candidate as primary
        primary_section = target_sections[0]
        actual_title = primary_section.get('title', '').strip()
        display_title = actual_title if actual_title else "[Empty]"
        section_ref = "Section 7 - Test Objective"

        # Normalization: Remove trailing colon for comparison
        norm_actual = actual_title.rstrip(':').strip()
        norm_expected = expected_title.rstrip(':').strip()
        
        if norm_actual != norm_expected:
            errors.append({
                "where": section_ref,
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })

        # Content Check
        content = primary_section.get('content', [])
        has_meaningful = False
        
        # Also check 'test_objective' field if it exists (from structured extraction)
        if 'test_objective' in primary_section:
             obj_text = primary_section['test_objective']
             if isinstance(obj_text, str) and is_meaningful_content(obj_text):
                 has_meaningful = True
        
        if not has_meaningful:
            for item in content:
                text = item.get('text', '') if isinstance(item, dict) else str(item)
                if is_meaningful_content(text):
                    has_meaningful = True
                    break

        if not has_meaningful:
           errors.append({
               "where": section_ref, 
               "what": "Test objective is missing or non-descriptive", 
               "suggestion": "Add a clear test objective", 
               "redirect_text": f"{actual_title}"
           })
        
        return errors if errors else None

    except Exception as e:
        return [{"where": "Section 7", "what": f"Error: {e}", "suggestion": "Check file structure"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_7(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result if result else [], f, indent=4)
    if result: print(json.dumps(result, indent=4))
