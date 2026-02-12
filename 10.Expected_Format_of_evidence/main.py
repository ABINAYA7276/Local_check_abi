import json
import os
import sys

def check_section_10(file_path):
    """
    Validates Section 10: Expected Format of Evidence.
    Checks for: 
    1. Section existence.
    2. Title correctness.
    3. Content presence.
    Returns findings in fixed JSON format.
    """
    findings = []
    
    if not os.path.exists(file_path):
        return [{
            "where": "File Status",
            "what": "File not found",
            "suggestion": f"Ensure file '{file_path}' exists",
            "redirect_text": "File missing"
        }]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        target_section = None
        target_id = 'Unknown'
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            sec_id = section.get('section_id', '')

            # HARD GUARD
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11', 'SEC-12', 'SEC-13']:
                continue

            # Strict Logic for Section 10
            is_section_10 = False
            
            # Match SEC-14 (standard for 10)
            if sec_id == 'SEC-14':
                is_section_10 = True
            
            # Match title '10.' AND 'Format' or 'Evidence'
            elif title.startswith('10.') and ('format' in title_lower or 'evidence' in title_lower):
                is_section_10 = True
            
            if is_section_10:
                target_section = section
                target_id = sec_id
                break
        
        if not target_section:
            return [{
                "where": "10. Expected Format of Evidence:",
                "what": "Section 10 missing",
                "suggestion": "Add Section 10 - Expected Format of Evidence",
                "redirect_text": "10. Expected Format of Evidence:"
            }]
        
        # 1. Check Title Correctness
        actual_title = target_section.get('title', '').strip()
        expected_title = "10. Expected Format of Evidence:"
        
        # Clean title for display/redirect: Remove leading numbering (e.g. "10.", "89.", "12.1.") whilst keeping spaces
        import re
        redirect_title = re.sub(r'^[\d\.]+\s*', '', actual_title).strip()
        
        if actual_title != expected_title:
            findings.append({
                "where": expected_title,
                "what": f"title mismatch. Found: '{redirect_title}'",
                "suggestion": f"Correct title to '{expected_title}'",
                "redirect_text": redirect_title
            })
            
        # 2. Check Content Presence
        has_text = False
        
        # Check in 'expected_format_of_evidence' field
        expected_format = target_section.get('expected_format_of_evidence', '')
        if expected_format and str(expected_format).strip():
            expected_format_lower = str(expected_format).strip().lower()
            if (expected_format_lower and 
                expected_format_lower not in ['none', 'n/a', 'nil', '.', '-', '_', '...'] and
                len(str(expected_format).strip()) > 2 and
                not all(c in '.-_,;:!? ' for c in str(expected_format).strip())):
                has_text = True
        
        # Check in 'content' field
        if not has_text:
            content = target_section.get('content', [])
            for item in content:
                text = ""
                if isinstance(item, dict):
                    text = item.get('text', '').strip()
                elif isinstance(item, str):
                    text = item.strip()
                
                if text:
                    text_lower = text.lower()
                    if (text_lower not in ['none', 'n/a', 'nil', '.', '-', '_', '...'] and
                        len(text) > 2 and
                        not all(c in '.-_,;:!? ' for c in text)):
                        has_text = True
                        break
        
        if not has_text:
            found_desc = str(expected_format).strip() if expected_format else ""
            findings.append({
                "where": expected_title,
                "what": f"content missing. Found: '{found_desc}'",
                "suggestion": "Add Expected Format of Evidence content",
                "redirect_text": redirect_title
            })
        
        # Final output structure
        return findings

    except Exception as e:
        return [{
            "where": "Processing Error",
            "what": str(e),
            "suggestion": "Check file format and try again",
            "redirect_text": "Parsing error"
        }]

if __name__ == "__main__":
    # Get path from command line arg or use default
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_10(json_path)
    
    # Save to output.json
    # Save to output.json (silent)
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
    except Exception:
        pass
    
    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1)
    else:
        sys.exit(0)
