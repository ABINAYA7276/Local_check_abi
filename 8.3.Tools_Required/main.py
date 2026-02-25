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
            
            title_lower = title.lower()
            # Match '8.3', 'tools', and 'required' in the title
            if '8.3' in title and 'tools' in title_lower and 'required' in title_lower:
                candidates.append(section)
        
        if not candidates:
             return [{
                "where": expected_title,
                "what": "Section 8.3 missing",
                "suggestion": f"Add {expected_title}",
                "severity": "high"
            }]
        
        primary_section = candidates[0]
        actual_title = primary_section.get('title', '').strip()
        # Clean redirect title (remove leading numbers and "Required")
        redirect_title = re.sub(r'^[\d\.]+\s*', '', actual_title).strip() or actual_title
        if "tools" in redirect_title.lower() and "required" in redirect_title.lower():
            redirect_title = "Tools Required"
        errors = []

        # 2. Title Validation
        if actual_title.replace(':', '').strip().lower() != expected_title.replace(':', '').strip().lower():
             return [{
                "where": expected_title,
                "what": "Section 8.3 missing",
                "suggestion": f"Add {expected_title}",
                "severity": "high"
            }]
        
        # 3. Tools Content Validation
        tools = primary_section.get('tools', [])
        
        def is_meaningful(t):
            t_str = t.get('tool', '').strip() if isinstance(t, dict) else str(t).strip()
            return t_str and t_str.lower() not in ['.', '-', '...', '---', 'nil', 'n/a', 'none']

        has_meaningful_content = any(is_meaningful(t) for t in tools)

        if not tools or not has_meaningful_content:
             # ONE single high-severity message for missing content
             errors.append({
                "where": actual_title,
                "what": "content missing. Found empty tool entries.",
                "suggestion": "Provide the name and version for each required tool (e.g., 'Putty v (0.83)').",
                "redirect_text": redirect_title,
                "severity": "high"
            })
             return errors # Stop here if everything is empty
        
        # 4. Detail Validation (Only if some content exists)
        version_pattern = r'v\s*\(?\s*\d+(\.\d+)*\s*\)?'
        for idx, tool in enumerate(tools):
                val = tool.get('tool', '').strip() if isinstance(tool, dict) else str(tool).strip()
                
                if not val:
                    errors.append({
                        "where": f"{actual_title} - Tool {idx+1}",
                        "what": f"Tool {idx+1} entry is empty",
                        "suggestion": "Provide the tool name and version (e.g., 'Putty v (0.83)')",
                        "redirect_text": redirect_title,
                        "severity": "high"
                    })
                    continue

                # Check for Version ID
                # Must contain 'v' followed by digits (e.g. v7.95.0 or v (0.83))
                is_version_valid = re.search(version_pattern, val, re.IGNORECASE)
                if 'v ()' in val or 'v()' in val: is_version_valid = False

                # Check if tool name exists before the 'v'
                # Find the start of the version string
                version_match = re.search(r'\bv\s*\(?\s*\d+', val, re.IGNORECASE)
                tool_name_missing = False
                if version_match:
                    prefix = val[:version_match.start()].strip()
                    if not prefix:
                        tool_name_missing = True

                if not is_version_valid:
                     error_msg = f"Version number missing: Found '{val}' in Section 8.3 Tools Required"
                     if not re.search(r'\bv\b', val, re.IGNORECASE):
                         error_msg = f"Version identifier 'v' missing: Found '{val}' in Section 8.3 Tools Required"
                     
                     # Try to construct a better suggestion
                     suggested_val = val
                     if " 'v' missing" in error_msg:
                         # Insert 'v' before the likely version part
                         suggested_val = re.sub(r'(\(?\d+)', r'v \1', val, count=1)
                     elif "Version number missing" in error_msg:
                         suggested_val = val.replace('()', '(Version Number)') if '()' in val else f"{val} (Version Number)"

                     errors.append({
                         "where": f"Section 8.3 - Tools Required - {val}",
                         "what": error_msg,
                         "suggestion": f"Expected: '{suggested_val}'",
                         "redirect_text": redirect_title, 
                         "severity": "medium"
                    })
                elif tool_name_missing:
                     errors.append({
                         "where": f"Section 8.3 - Tools Required - {val}",
                         "what": f"Tool name missing: Found '{val}' in Section 8.3 Tools Required",
                         "suggestion": f"Expected: '[Tool Name] {val}'",
                         "redirect_text": redirect_title,
                         "severity": "high"
                    })

        return errors

    except Exception as e:
        return [{"where": "Section 8.3", "what": f"Error: {e}", "severity": "high"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_3(json_path)
    # Save to output.json (silent)
    try:
        # Sort by severity
        severity_priority = {"high": 0, "medium": 1, "low": 2}
        result.sort(key=lambda x: severity_priority.get(x.get('severity', 'medium'), 1))
        
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result if result else [], f, indent=4)
    except Exception:
        pass

    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1)


    else:
        sys.exit(0)
