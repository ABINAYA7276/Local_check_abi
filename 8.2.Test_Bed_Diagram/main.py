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
            sec_id = section.get('section_id', '')
            
            # HARD GUARD
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-11', 'SEC-12']:
                continue

            # Strict Logic
            if sec_id == 'SEC-10':
                candidates.append(section)
                continue
            
            if title.startswith('8.2') and not title.startswith('8.2.'):
                candidates.append(section)
        
        if not candidates:
            return [{"where": "Section 8.2 - Test Bed Diagram", "what": "Section 8.2 missing", "suggestion": f"Add {expected_title}", "redirect_text": f"{expected_title}"}]
        
        primary_section = candidates[0]
        actual_title = primary_section.get('title', '').strip()
        
        # Title Validation
        norm_actual = actual_title.replace(':', '').strip().lower()
        norm_expected = expected_title.replace(':', '').strip().lower()
        
        # Allow slight title variations if minor punct difference, but strict otherwise
        if norm_actual != norm_expected:
             errors.append({
                "where": "Section 8.2 - Test Bed Diagram",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })

        # Content Validation
        content = primary_section.get('content', [])
        has_valid_figure = False
        
        found_figure_text = ""
        
        for item in content:
            text = ""
            if isinstance(item, dict):
                 text = item.get('text', '').strip()
            else:
                 text = str(item).strip()
            
            text_lower = text.lower()
            if 'figure' in text_lower:
                found_figure_text = text
            
            # Strict Check for Figure 8.2.1
            if 'figure' in text_lower and '8.2.1' in text:
                has_valid_figure = True
                break
        
        if not has_valid_figure:
             what_msg = f"Incorrect Figure ID or missing diagram: Found '{found_figure_text}'" if found_figure_text else "Test Bed Diagram figure missing"
             errors.append({
                "where": "Section 8.2 - Test Bed Diagram",
                "what": what_msg,
                "suggestion": "Ensure exactly 'Figure 8.2.1: Test-bed Diagram'",
                "redirect_text": f"{actual_title}"
            })

        return errors

    except Exception as e:
        return [{"where": "Section 8.2", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_2(json_path)
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
