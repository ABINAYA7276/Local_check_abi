import json
import os
import re
import sys

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
        target_section = None
        standard_title = "8.3. Tools Required"
        stable_redirect = "Tools Required"
        
        # 1. IDENTIFICATION (by static title body)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Identify by keywords: 'tools' and 'required'
            if 'tools' in title_lower and 'required' in title_lower:
                # Exclude numerical subsections (e.g. 8.3.1)
                if re.search(r'^\d+\.\d+\.\d+', title):
                    continue
                target_section = section
                break
        
        if not target_section:
             return [{
                "where": standard_title,
                "what": "Section 8.3 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body (Strict validation)
        has_correct_body = 'tools required' in title_lower

        # Identify any leading number prefix (handles 8.3., 8.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("8.3.")

        errors = []
        
        # 1. Number Checks
        expected_num = standard_title.split(' ')[0]
        if not has_correct_num:
            if has_any_number:
                wrong_num = num_prefix_match.group(1).strip()
                errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '{expected_num}'",
                    "suggestion": f"Replace section number '{wrong_num}' with '{expected_num}'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            else:
                errors.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix '{expected_num}'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })

        # 2. Body / Formatting Checks (Spacing)
        has_tools_body = 'tools' in title_lower and 'required' in title_lower
        
        if has_tools_body:
            if not has_correct_body:
                errors.append({
                    "where": standard_title,
                    "what": f"Incorrect formatting or missing space in the title. Found: '{found_title}'",
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
        else:
            # Title is entirely wrong or absent
            return [{
                "where": standard_title,
                "what": "Section 8.3 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "High"
            }]
             
        # proceed to content check if we have the body
        
        actual_title = found_title
        # Clean redirect: Remove leading numbers/dots and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect
        
        # 3. Tools Content Validation
        tools = target_section.get('tools', [])
        
        def is_meaningful(t):
            t_str = t.get('tool', '').strip() if isinstance(t, dict) else str(t).strip()
            return t_str and t_str.lower() not in ['.', '-', '...', '---', 'nil', 'n/a', 'none']

        has_meaningful_content = any(is_meaningful(t) for t in tools)

        if not tools or not has_meaningful_content:
             # ONE single high-severity message for missing content
             errors.append({
                "where": standard_title,
                "what": "content missing. Found empty tool entries.",
                "suggestion": "Provide the name and version for each required tool (e.g., 'Putty v (0.83)').",
                "redirect_text": found_title,
                "severity": "High"
            })
             # Only return if we truly have nothing to check version-wise
             if not tools: return errors 
        
        # 4. Detail Validation (Only if some content exists)
        version_pattern = r'v\s*\(?\s*\d+(\.\d+)*\s*\)?'
        for idx, tool in enumerate(tools):
                val = tool.get('tool', '').strip() if isinstance(tool, dict) else str(tool).strip()
                
                if not val:
                    errors.append({
                        "where": f"{standard_title} - Tool {idx+1}",
                        "what": f"Tool {idx+1} entry is empty",
                        "suggestion": "Provide the tool name and version (e.g., 'Putty v (0.83)')",
                        "redirect_text": found_title,
                        "severity": "High"
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
                         "where": f"{standard_title} - {val}",
                         "what": error_msg,
                         "suggestion": f"Expected: '{suggested_val}'",
                         "redirect_text": found_title, 
                         "severity": "Medium"
                    })
                elif tool_name_missing:
                     errors.append({
                         "where": f"{standard_title} - {val}",
                         "what": f"Tool name missing: Found '{val}' in Section 8.3 Tools Required",
                         "suggestion": f"Expected: '[Tool Name] {val}'",
                         "redirect_text": found_title,
                         "severity": "High"
                    })

        return errors

    except Exception as e:
        return [{"where": "Section 8.3", "what": f"Error: {e}", "severity": "High"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_3(json_path)
    # Save to output.json (silent)
    try:
        # SORTING: Title issues (Low/Medium) before Content issues (High)
        severity_priority = {"Low": 0, "Medium": 1, "High": 2}
        if isinstance(result, list):
            result.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium').capitalize(), 1))
        
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result if result else [], f, indent=4)
    except Exception:
        pass

    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1)


    else:
        sys.exit(0)
