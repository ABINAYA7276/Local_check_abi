
import json
import os
import re
import sys

def check_section_4(file_path):
    """
    Checks Section 4 using Simplified Concept.
    Focuses on 'DUT Interface Status details' table validation.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 4", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        stable_redirect = "DUT Interface Status details"
        
        standard_title = "4. DUT Confirmation Details"

        # 1. IDENTIFICATION (by static title body)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Relaxed Identification
            if 'dut' in title_lower and 'confirmation' in title_lower:
                 candidates.append(section)
        
        if not candidates:
            return [{
                "where": standard_title,
                "what": "Section 4 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": stable_redirect,
                "severity": "High"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        primary_section = candidates[0]
        found_title = primary_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body
        has_dut_body = "dut confirmation details" in title_lower

        # Identify any leading number prefix (handles 4., 4.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("4.")

        errors = []
        if not (has_correct_num and has_dut_body):
            if has_dut_body and has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = num_prefix_match.group(1).strip()
                errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '4.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '4.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_dut_body and not has_any_number:
                # Title body is correct but section number "4." is missing entirely
                errors.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })
            else:
                # Title is entirely wrong or absent
                return [{
                    "where": standard_title,
                    "what": "Section 4 missing",
                    "suggestion": f"Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "High"
                }]
            # proceed to content check if we have the body
        
        actual_title = found_title
        # Clean redirect: Remove leading numbers and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect
        
        # Helper to check meaningful text
        def is_valid_content(t):
            if not t or not isinstance(t, str): return False
            t_clean = t.strip()
            if t_clean.lower() in ['none', 'n/a', 'nil', 'tbd', '...', '---', '', '.']: return False
            return True

        # 2A. GENERAL CONTENT VALIDATION (High Severity)
        has_any_content = False
        content_sources = []
        
        # Gather all text content
        if 'dut_details' in primary_section:
            details = primary_section['dut_details']
            if isinstance(details, list):
                # If it's a list of strings, combine them. 
                # If it's a list of dicts (normal behavior), we'll handle that in the loop below.
                if details and isinstance(details[0], str):
                    content_sources.append(" ".join([str(i) for i in details if i]))
                else:
                    content_sources.extend(details)
            else:
                content_sources.append(str(details))
            
        if 'content' in primary_section:
            content = primary_section['content']
            if isinstance(content, list):
                if content and isinstance(content[0], str):
                    content_sources.append(" ".join([str(i) for i in content if i]))
                else:
                    content_sources.extend(content)
            else:
                content_sources.append(str(content))

        found_text_sample = ""
        for item in content_sources:
            text = ""
            if isinstance(item, str): text = item
            elif isinstance(item, dict):
                # Images NO LONGER count as content (Consistent with Section 5)
                if item.get('type') == 'image' or item.get('image_path'):
                    continue
                # Ignore table structures for general content check
                if item.get('type') != 'table':
                    text = item.get('text', '')
            
            if is_valid_content(text):
                has_any_content = True
                break
            elif text and not found_text_sample:
                found_text_sample = text
        
        if not has_any_content:
             errors.append({
                "where": actual_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the DUT confirmation details.",
                "redirect_text": redirect_val,
                "severity": "High"
            })
            # Do NOT return here. Continue to check the table.

        # 2B. TABLE VALIDATION (Medium Severity)
        found_table = False
        
        # Search in 'dut_details' or 'content'
        search_fields = [primary_section.get('dut_details', []), primary_section.get('content', [])]
        
        for field in search_fields:
            items = field if isinstance(field, list) else ([field] if field else [])
            
            # Look for the specific table structure
            for item in items:
                if isinstance(item, dict) and item.get('type') == 'table':
                    headers = item.get('headers', [])
                    
                    # Improved Identification: Check for ANY relevant keyword match
                    # This allows finding the table even if headers are incorrect/missing
                    header_str = " ".join([str(h).lower() for h in headers])
                    keywords = ['interface', 'port', 'type', 'name']
                    match_count = sum(1 for k in keywords if k in header_str)
                    
                    # If at least ONE keyword matches, assume it's the target table
                    if match_count >= 1:
                        found_table = True
                        
                        expected_headers = ["Interfaces", "No.of Ports", "Interface Type", "Interface Name"]
                        
                        # Validate Headers
                        for idx, exp in enumerate(expected_headers):
                            if idx < len(headers):
                                h = str(headers[idx]).strip()
                                # Normalize for comparison
                                h_norm = h.lower().replace(' ', '').replace('.', '').replace('_', '')
                                exp_norm = exp.lower().replace(' ', '').replace('.', '').replace('_', '')
                                
                                if not h:
                                     # Empty header found -> "Missing table header"
                                     errors.append({
                                        "where": actual_title,
                                        "what": f"Missing table header at Column {idx+1}",
                                        "suggestion": f"Provide the correct header: '{exp}'",
                                        "redirect_text": redirect_val,
                                        "severity": "Medium"
                                    })
                                elif h_norm != exp_norm:
                                     # Wrong text found -> "Incorrect table header found"
                                    errors.append({
                                        "where": actual_title,
                                        "what": f"Incorrect table header found: '{h}'",
                                        "suggestion": f"Provide the correct header: '{exp}'",
                                        "redirect_text": redirect_val,
                                        "severity": "Medium"
                                    })
                            else:
                                # Header index out of range -> "Missing table header" (effectively missing column)
                                errors.append({
                                    "where": actual_title,
                                    "what": f"Missing table header at Column {idx+1}",
                                    "suggestion": f"Provide the correct header: '{exp}'",
                                    "redirect_text": redirect_val,
                                    "severity": "Medium"
                                })
                        
                        # Validate Rows (Cell-specific validation)
                        rows = item.get('rows', [])
                        if not rows:
                             errors.append({
                                "where": actual_title,
                                "what": "Table content is empty",
                                "suggestion": "Provide the DUT interface status details table content.",
                                "redirect_text": redirect_val,
                                "severity": "Medium"
                            })
                        else:
                            for r_idx, row in enumerate(rows, 1):
                                for c_idx, cell in enumerate(row):
                                    # Identify specific column name (or fallback)
                                    col_name = headers[c_idx] if c_idx < len(headers) and str(headers[c_idx]).strip() else f"Column {c_idx+1}"
                                    
                                    if not str(cell).strip():
                                        errors.append({
                                            "where": actual_title,
                                            "what": f"Missing value in Row {r_idx}, Column '{col_name}'",
                                            "suggestion": f"Provide the '{col_name}' details.",
                                            "redirect_text": redirect_val,
                                            "severity": "Medium"
                                        })
                        break 
            if found_table: break

        if not found_table:
             errors.append({
                "where": actual_title,
                "what": "DUT Interface Status details table is missing",
                "suggestion": "Provide the DUT interface status details table.",
                "redirect_text": redirect_val,
                "severity": "Medium"
            })

        # Sort by severity
        severity_priority = {"High": 0, "Medium": 1, "Low": 2}
        errors.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
            
        return errors

    except Exception as e:
        return [{"where": "Section 4", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_4(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)
    print(json.dumps(result, indent=4))

