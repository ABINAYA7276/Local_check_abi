import json
import os
import sys
import re

def check_section_8_2(file_path):
    """
    Validate Section 8.2 (Test Bed Diagram).
    Checks for presence, correct title, and diagram/figure reference.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 8.2", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        errors = []
        expected_title = "8.2. Test Bed Diagram"

        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Match keywords: '8.2', 'test', 'bed', 'diagram'
            if '8.2' in title and 'test' in title_lower and 'bed' in title_lower and 'diagram' in title_lower:
                candidates.append(section)
        
        if not candidates:
            return [{
                "where": expected_title, 
                "what": "Section 8.2 missing", 
                "suggestion": f"Add {expected_title}", 
                "severity": "high"
            }]
        
        primary_section = candidates[0]
        actual_title = primary_section.get('title', '').strip()
        # Clean Redirect Text: Remove leading number, spaces, or colon
        redirect_title = re.sub(r'^\d+\.\d?\.\s*', '', actual_title).strip()
        
        # Title Validation
        norm_actual = actual_title.replace(':', '').strip().lower()
        norm_expected = expected_title.replace(':', '').strip().lower()
        
        if norm_actual != norm_expected:
             return [{
                "where": expected_title,
                "what": "Section 8.2 missing",
                "suggestion": f"Add {expected_title}",
                "severity": "high"
            }]

        # Content Validation
        content = primary_section.get('content', [])
        has_perfect_figure = False
        found_any_figure = False
        id_correct = False
        name_correct = False
        best_candidate = ""
        
        for item in content:
            text = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
            text_lower = text.lower()
            
            if 'figure' in text_lower:
                found_any_figure = True
                best_candidate = text
                
                # Check ID
                curr_id_correct = '8.2.1' in text
                # Check Name
                # Check Name: Allow spaces or hyphens between words, but ensure it ends exactly at 'diagram'
                curr_name_correct = bool(re.search(r'test[\s\-]+bed[\s\-]+diagram\b', text_lower))
                
                if curr_id_correct and curr_name_correct:
                    has_perfect_figure = True
                    break
                
                # Track best candidate (the one with the most correct parts)
                if curr_id_correct: id_correct = True
                if curr_name_correct: name_correct = True
        
        if not has_perfect_figure:
            if not found_any_figure:
                errors.append({
                    "where": f"{actual_title} - Figure Check",
                    "what": "Figure ID and Name are missing.",
                    "suggestion": "Expected: 'Figure 8.2.1: Test Bed Diagram'",
                    "redirect_text": redirect_title,
                    "severity": "high"
                })
            else:
                if not id_correct:
                    # If some numbers exist, call it 'incorrect', otherwise 'missing'
                    id_status = "incorrect" if re.search(r'\d', best_candidate) else "missing"
                    errors.append({
                        "where": f"{actual_title} - Figure ID Check",
                        "what": f"Figure ID is {id_status}: Found '{best_candidate}'.",
                        "suggestion": "Expected ID: '8.2.1'",
                        "redirect_text": redirect_title,
                        "severity": "high" if id_status == "missing" else "low"
                    })
                if not name_correct:
                    # If some text exists after 'Figure', call it 'incorrect', otherwise 'missing'
                    # We check if there's any alphabetical text besides 'Figure'
                    name_status = "incorrect" if re.search(r'[a-z]{3,}', best_candidate.lower().replace('figure', '')) else "missing"
                    errors.append({
                        "where": f"{actual_title} - Figure Name Check",
                        "what": f"Figure name is {name_status}: Found '{best_candidate}'.",
                        "suggestion": "Expected Name: 'Test Bed Diagram'",
                        "redirect_text": redirect_title,
                        "severity": "high" if name_status == "missing" else "medium"
                    })

        return errors

    except Exception as e:
        return [{"where": "Section 8.2", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_2(json_path)
    
    # Sort by severity
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
