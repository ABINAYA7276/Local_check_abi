import json
import os
import sys
import re

def check_section_8_3(file_path):
    """
    Validate Section 8.3 (Tools Required).
    Checks for presence, title correctness, and tool version formats.
    Ignores sections that clearly belong to other parts of the document.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 8.3", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        expected_title = "8.3. Tools Required"
        
        # 1. Identify Section 8.3 candidates
        # Exclusion keywords to avoid other sections
        other_section_keywords = [
            'itsar section', 'security requirement', 'requirement description', 
            'dut confirmation', 'dut configuration', 'precondition', 
            'test objective', 'test plan', 'test execution', 'test case'
        ]

        for section in sections:
            title = section.get('title', '').strip()
            sec_id = section.get('section_id', '')
            
            # HARD GUARD
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-12']:
                continue

            # Strict Logic
            if sec_id == 'SEC-11':
                candidates.append(section)
                continue
            
            if title.startswith('8.3') and not title.startswith('8.3.'):
                candidates.append(section)
        
        if not candidates:
             return [{
                "where": "Section 8.3 - Tools Required",
                "what": "Section 8.3 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]
        
        primary_section = candidates[0]
        actual_title = primary_section.get('title', '').strip()
        errors = []
        
        # Title Validation
        norm_actual = actual_title.replace(':', '').strip().lower()
        norm_expected = expected_title.replace(':', '').strip().lower()
        
        if norm_actual != norm_expected:
             errors.append({
                "where": "Section 8.3 - Tools Required",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })

        # Tools Validation
        tools = primary_section.get('tools', [])
        
        # Fallback to content if 'tools' array is empty (handle legacy format)
        if not tools:
            # Logic could be added here to parse content text if needed, 
            # for now assume tools array must be populated or it's an error.
            pass

        if not tools:
             errors.append({
                "where": "Section 8.3 - Tools Required",
                "what": "Tools list is empty or missing",
                "suggestion": "List required tools with versions",
                "redirect_text": f"{actual_title}"
            })
        else:
            version_pattern = r'v\s*\(?\s*\d+(\.\d+)*\s*\)?'
            for idx, tool in enumerate(tools):
                val = tool.get('tool', '').strip() if isinstance(tool, dict) else str(tool).strip()
                
                if not val:
                    continue

                # Check for Version ID
                # Must contain 'v' followed by digits (e.g. v7.95.0 or v (0.83))
                # Also explicitly check for empty parens like v () which is invalid
                is_valid = re.search(version_pattern, val, re.IGNORECASE)
                if 'v ()' in val or 'v()' in val: is_valid = False

                if not is_valid:
                     errors.append({
                         "where": "Section 8.3 - Tools Required",
                         "what": f"Tool version missing or invalid format: '{val}'",
                         "suggestion": "Ensure format includes version checks (e.g., v7.95.0 or v (0.83))",
                         "redirect_text": f"{actual_title}"
                    })

        return errors

    except Exception as e:
        return [{"where": "Section 8.3", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_3(json_path)
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
