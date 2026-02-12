import sys
import os
import re
import json

def check_section_12(file_path):
    """
    Validate Section 12: Test Case Result.
    """
    if not os.path.exists(file_path):
        return [{
            "where": "Section 12 - Test Case Result",
            "what": "File not found at path",
            "suggestion": "Provide a valid JSON file path"
        }]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        errors = []
        target_sections = []
        expected_title = "12. Test Case Result:"
        
        # Base ID extraction (Layer 2 logic)
        base_id = None
        
        target_sections = []
        base_id = None
        
        # 1. Base ID search (Section 2/3)
        for section in sections:
            sec_id = section.get('section_id', '')
            if sec_id in ['SEC-02', 'SEC-03']:
                 # ... existing logic to find base_id ...
                 text_content = str(section)
                 match = re.search(r'(\d+\.\d+\.\d+)', text_content)
                 if match:
                     base_id = match.group(1)
                     break
        
        # 2. Strict Section 12 Detection
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            sec_id = section.get('section_id', '')

            # HARD GUARD
            if sec_id in [f'SEC-{i:02d}' for i in range(1, 16)]:
                continue

            is_section_12 = False
            
            # Match SEC-16 (standard for 12), but ensure title doesn't look like Section 11
            if sec_id == 'SEC-16':
                if not title.startswith('11.'):
                    is_section_12 = True
            
            # Match title '12.' AND ('Result' or common typo 'Rest')
            elif title.startswith('12.') and ('result' in title_lower or 'rest' in title_lower):
                is_section_12 = True
            
            if is_section_12:
                target_sections.append(section)

        if not target_sections:
            return [{
                "where": "12. Test Case Result:",
                "what": "Section 12 missing",
                "suggestion": "Expected: '12. Test Case Result:'",
                "redirect_text": "12. Test Case Result:"
            }]

        for idx, target_section in enumerate(target_sections):
            actual_title = target_section.get('title', '').strip()
            # Clean title for redirect_text: Remove leading numbering (e.g. "12.")
            redirect_title = re.sub(r'^\d+\.\s*', '', actual_title)
            
            level = target_section.get('level', 0)
            section_ref = "12. Test Case Result:"
            
            if level != 1:
                errors.append({
                    "where": section_ref, 
                    "what": f"Incorrect header level: Found level {level}", 
                    "suggestion": "Expected: level 1", 
                    "redirect_text": redirect_title
                })

            if actual_title != expected_title:
                errors.append({
                    "where": section_ref, 
                    "what": f"Incorrect title: Found '{actual_title}'", 
                    "suggestion": f"Expected: '{expected_title}'", 
                    "redirect_text": redirect_title
                })

            if idx == 0:
                # Check if Base ID was found/inferred
                if not base_id:
                    errors.append({
                        "where": section_ref,
                        "what": "Base ID is missing (Alignment check skipped)",
                        "suggestion": "Update Section 2/3 with a valid ID (e.g., 1.1.1: Name)",
                        "redirect_text": redirect_title
                    })

                # Handle Table Format (new)
                tc_results_table = target_section.get('test_case_results', {})
                # Handle List Format (old)
                tc_results_list = target_section.get('test_results', [])

                # Fallback: Infer Base ID from the first row if not found in metadata
                if not base_id:
                    first_id = None
                    if tc_results_table and tc_results_table.get('rows'):
                        # Try to get ID from first row, column index 1
                        rows = tc_results_table.get('rows')
                        if len(rows) > 0 and len(rows[0]) > 1:
                            first_id = str(rows[0][1]).strip()
                    elif tc_results_list:
                         # Try list format
                         if len(tc_results_list) > 0:
                             first_id = tc_results_list[0].get('test_case_id')

                    if first_id:
                        # Expecting format like 1.1.1.1 or 1.2.3.1
                        # We extract the prefix (everything before the last dot)
                        match = re.search(r'^(\d+(\.\d+)+)\.\d+$', first_id)
                        if match:
                            base_id = match.group(1)

                if tc_results_table:
                    headers = tc_results_table.get('headers', [])
                    rows = tc_results_table.get('rows', [])
                    
                    # Header check - lenient on Case Name/No
                    expected_headers_std = ["S. No", "TEST CASE No.", "PASS FAIL", "Remarks"]
                    
                    # Check if headers match standard OR acceptable variants
                    headers_valid = False
                    if headers == expected_headers_std:
                        headers_valid = True
                    elif len(headers) == 4 and headers[0] == "S. No" and headers[2] == "PASS FAIL" and headers[3] == "Remarks":
                        # Allow variations for column 2
                        if headers[1] in ["TEST CASE NAME", "TEST CASE NO", "TEST CASE NO.", "Test Case ID"]:
                            headers_valid = True
                    
                    if not headers_valid:
                        # Report mismatch
                        errors.append({"where": section_ref, "what": f"Incorrect table headers: Found {headers}", "suggestion": f"Expected: {expected_headers_std} (or 'TEST CASE NAME')", "redirect_text": redirect_title})

                    if not rows:
                        errors.append({"where": section_ref, "what": "Table rows are missing in 'rows' field", "suggestion": "Add test result data to rows", "redirect_text": redirect_title})
                    else:
                        for ridx, row in enumerate(rows, 1):
                            if len(row) < 4:
                                errors.append({"where": f"{section_ref} - Row #{ridx}", "what": f"Incomplete row data: Found {len(row)} columns", "suggestion": "Ensure each row has 4 columns", "redirect_text": redirect_title})
                                continue
                            
                            s_no = str(row[0]).strip()
                            tc_id = str(row[1]).strip()
                            status = str(row[2]).strip()
                            remarks = str(row[3]).strip()
                            
                            expected_id = f"{base_id}.{ridx}" if base_id else f"[ID].{ridx}"
                            entry_ref = f"{section_ref} - {expected_id}"

                            # S. No Check
                            if s_no != str(ridx):
                                errors.append({"where": entry_ref, "what": f"Incorrect sequence: Found '{s_no}' in 'S. No' column", "suggestion": f"Expected: '{ridx}'", "redirect_text": redirect_title})

                            # ID Check
                            if not tc_id:
                                errors.append({"where": entry_ref, "what": "Test Case ID is missing in 'TEST CASE No.' column", "suggestion": f"Expected: '{expected_id}'", "redirect_text": redirect_title})
                            elif tc_id != expected_id:
                                errors.append({"where": entry_ref, "what": f"Incorrect sequence: Found '{tc_id}' in 'TEST CASE No.' column", "suggestion": f"Expected: '{expected_id}'", "redirect_text": redirect_title})

                            # Status Check
                            if not status:
                                errors.append({"where": entry_ref, "what": "Result status is missing in 'PASS FAIL' column", "suggestion": "Expected: PASS/FAIL/NA", "redirect_text": redirect_title})
                            elif status.upper() not in ["PASS", "FAIL", "NA"]:
                                errors.append({"where": entry_ref, "what": f"Invalid status: Found '{status}' in 'PASS FAIL' column", "suggestion": "Expected: PASS, FAIL, or NA", "redirect_text": redirect_title})

                            # Remarks Check
                            if not remarks or remarks in ['.', '...']:
                                found_val = f"'{remarks}'" if remarks else "empty"
                                errors.append({"where": entry_ref, "what": f"Remarks are non-descriptive: Found {found_val} in 'Remarks' column", "suggestion": "Add meaningful observations", "redirect_text": redirect_title})

                elif tc_results_list:
                    for tidx, res in enumerate(tc_results_list, 1):
                        tc_id = res.get('test_case_id', '').strip()
                        status = res.get('result', '').strip()
                        remarks = res.get('remarks', '').strip()
                        
                        expected_id = f"{base_id}.{tidx}" if base_id else f"[ID].{tidx}"
                        entry_ref = f"{section_ref} - {expected_id}"
                        
                        if not tc_id:
                            errors.append({"where": entry_ref, "what": "Test Case ID is missing in 'test_case_id' field", "suggestion": f"Expected: '{expected_id}'", "redirect_text": redirect_title})
                        else:
                            if len(tc_id.split()) > 3:
                                errors.append({"where": entry_ref, "what": f"Invalid ID format: Found statement '{tc_id[:30]}...' in 'test_case_id' field", "suggestion": f"Expected: '{expected_id}'", "redirect_text": redirect_title})
                            elif tc_id != expected_id:
                                errors.append({"where": entry_ref, "what": f"Incorrect sequence: Found '{tc_id}' in 'test_case_id' field", "suggestion": f"Expected: '{expected_id}'", "redirect_text": redirect_title})
                            
                        if not status:
                             errors.append({"where": entry_ref, "what": "Result status is missing in 'result' field", "suggestion": "Expected: PASS, FAIL, or NA", "redirect_text": redirect_title})
                        elif status.upper() not in ["PASS", "FAIL", "NA"]:
                             errors.append({"where": entry_ref, "what": f"Invalid status: Found '{status}' in 'result' field", "suggestion": "Expected: PASS, FAIL, or NA", "redirect_text": redirect_title})
                        if not remarks or remarks == '.':
                             found_val = f"'{remarks}'" if remarks else "empty"
                             errors.append({"where": entry_ref, "what": f"Remarks are non-descriptive: Found {found_val} in 'remarks' field", "suggestion": "Add meaningful observations", "redirect_text": redirect_title})
                else:
                     errors.append({"where": section_ref, "what": "Test results content is missing", "suggestion": "Add 'test_case_results' (table) or 'test_results' (list)", "redirect_text": redirect_title})

        return errors if errors else None

    except Exception as e:
        return [{"where": "Section 12", "what": f"Error: {e}"}]

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_12(json_path)
    
    # Always save to output.json first
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result if result else [], f, indent=4)
        # print("Validation results saved to output.json") # Optional: remove if UI strictly parses stdout
    except:
        pass

    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1) # Signal failure to UI
    else:
        # print(json.dumps([])) # Optional: print empty list for success?
        sys.exit(0)
