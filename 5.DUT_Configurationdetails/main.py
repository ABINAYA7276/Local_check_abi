import json
import os
import sys
import re

def is_valid_sentence(text):
    if not text or not isinstance(text, str): return False
    text = text.strip().strip('"\'""''')
    if not text: return False
    words = re.findall(r'[A-Za-z]+', text)
    return len(words) >= 3 and ' ' in text

def check_section_5(file_path):
    """
    Validate Section 5 (DUT Configuration details).
    Uses strict identification to avoid 'collapsing' with other sections like 3 or 4.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 5", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        expected_title = "5. DUT Configuration:"
        
        
        # 1. Strictly identify Section 5
        
        for section in sections:
            title = section.get('title', '').strip()
            sec_id = section.get('section_id', '')
            
            # HARD GUARD: Never process other known sections as SEC-05
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11', 'SEC-12']:
                continue

            # Strict logic: 
            # 1. Explicit ID 'SEC-05' matches
            # 2. Starts with '5.' (excluding '5.1')
            
            if sec_id == 'SEC-05':
                 candidates.append(section)
            elif title.startswith('5.') and not title.startswith('5.1'):
                 candidates.append(section)
        
        if not candidates:
            return [{
                "where": "Section 5 - DUT Configuration",
                "what": "Section 5 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]
        
        # 2. SELECT PRIMARY (For Title Check)
        primary_section = candidates[0] # Taking first match as primary
        
        errors = []
        actual_title = primary_section.get('title', '').strip()
        
        # Normalize title for comparison
        if actual_title != expected_title:
             errors.append({
                "where": "Section 5 - DUT Configuration",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })

        has_text = False
        invalid_text = ""
        
        # 3. Dynamic Content Aggregation
        for target in candidates:
            # Check 'dut_configuration' key first
            dut_conf = target.get('dut_configuration', '')
            if isinstance(dut_conf, list):
                for item in dut_conf:
                    text = item.get('text', '') if isinstance(item, dict) else str(item)
                    if is_valid_sentence(text):
                        has_text = True
                        break
            elif isinstance(dut_conf, str) and is_valid_sentence(dut_conf):
                has_text = True
            
            if has_text: break
            
            # Check generic content
            content = target.get('content', [])
            if isinstance(content, list):
                 for item in content:
                    text = item.get('text', '') if isinstance(item, dict) else str(item)
                    if is_valid_sentence(text):
                        has_text = True
                        break
                    elif text.strip() and not invalid_text:
                        invalid_text = text.strip()
            
            if has_text: break

        if not has_text:
            errors.append({
                "where": "Section 5 - DUT Configuration",
                "what": "Content missing",
                "suggestion": "Add credentials and services details",
                "redirect_text": f"{actual_title}"
            })
        return errors
    except Exception as e:
        return [{"where": "Section 5", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_5(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)
    print(json.dumps(result, indent=4))
