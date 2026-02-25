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
            "suggestion": "Provide a valid JSON file path",
            "severity": "high"
        }]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        errors = []
        target_sections = []
        expected_title = "12. Test Case Result:"
        
        # 1. Base ID search (Section 2/3)
        base_id = None

        for section in sections:
            sec_id = section.get('section_id', '')
            title = " ".join(section.get('title', '').split())
            title_lower = title.lower()

            # Optional: Check Section 1, 2 or 3 for base_id
            if not base_id:
                if sec_id in ['SEC-01', 'SEC-02', 'SEC-03'] or re.search(r'\b[123]\.', title):
                    # Check direct fields
                    for field in ['security_requirement', 'requirement_description']:
                        val = section.get(field, '')
                        if val:
                            match = re.search(r'\b(\d+\.\d+\.\d+)\b', str(val))
                            if match:
                                base_id = match.group(1)
                                break
                    if not base_id:
                        content = section.get('content', [])
                        for item in content:
                            text = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                            match = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                            if match:
                                base_id = match.group(1)
                                break
        
        # 2. Robust Section Discovery: Mandatory Keywords ["12", "test", "case", "result"]
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Identify the section by searching for mandatory keywords
            keywords = ["12", "test", "case", "result"]
            if all(kw in title_lower for kw in keywords):
                target_sections.append(section)

        if not target_sections:
            return [{
                "where": "12. Test Case Result:",
                "what": "Section 12 missing",
                "suggestion": "Expected: '12. Test Case Result:'",
                "redirect_text": "12. Test Case Result:",
                "severity": "high"
            }]

        for idx, target_section in enumerate(target_sections):
            actual_title = " ".join(target_section.get('title', '').split())
            # Clean redirect title (remove leading numbers)
            redirect_title = re.sub(r'^[\d\.]+\s*', '', actual_title).strip() or "Test Case Result"
            section_ref = "12. Test Case Result:"
            
            if target_section.get('level', 0) != 1:
                errors.append({"where": section_ref, "what": f"Incorrect header level: Found level '{target_section.get('level')}'. in {redirect_title}", "suggestion": "Expected: level 1", "redirect_text": redirect_title, "severity": "low"})

            def normalize(text):
                return " ".join(re.sub(r'[.:;/\-\(\)]', ' ', str(text)).lower().split())

            # 1. Flexible Title Check
            # Using same keywords as scoring for consistency
            title_norm = normalize(actual_title)
            is_valid_title = (title_norm.startswith("12 test case res") or 
                             title_norm.startswith("12 res") or 
                             title_norm == "12 results")
            
            # Strict title validation - if not exact enough, report as missing and stop
            if actual_title.replace(':', '').strip().lower() != expected_title.replace(':', '').strip().lower():
                errors.append({
                    "where": section_ref, 
                    "what": "Section 12 missing", 
                    "suggestion": f"Add {expected_title}", 
                    "redirect_text": redirect_title,
                    "severity": "high"
                })
                continue # Skip table processing for this section
            
            # Check if Table exists
            tc_results_table = target_section.get('test_case_results')
            if not tc_results_table:
                errors.append({
                    "where": section_ref,
                    "what": f"Test results table ('test_case_results') is missing. in {redirect_title}",
                    "suggestion": "Section 12 must contain a structured results table",
                    "redirect_text": redirect_title,
                    "severity": "high"
                })
                continue

            # Base ID Logic & Content Validation
            if idx == 0:
                # Fallback ID extraction from first row of table if base_id not found in SEC-02/03
                if not base_id:
                    rows = tc_results_table.get('rows', [])
                    if rows and len(rows[0]) > 1:
                         first_id = str(rows[0][1]).strip()
                         match = re.search(r'^(\d+(\.\d+)+)\.\d+$', first_id)
                         if match:
                             base_id = match.group(1)

                if not base_id:
                    errors.append({
                        "where": section_ref,
                        "what": "Base ID is missing (Alignment check skipped): Found empty in Section 2/3. in " + redirect_title,
                        "suggestion": "Update Section 2/3 with a valid ID (e.g., 1.1.1: Name)",
                        "redirect_text": redirect_title,
                        "severity": "low"
                    })

                headers = tc_results_table.get('headers', [])
                rows = tc_results_table.get('rows', [])
                
                if len(headers) != 4:
                     errors.append({"where": section_ref, "what": f"Incorrect table structure: Found {len(headers)} columns. in {redirect_title}", "suggestion": "Expected: ['S. No', 'TEST CASE No.', 'PASS FAIL', 'Remarks']", "redirect_text": redirect_title, "severity": "medium"})
                else:
                    # Column 0: (S. No, Sr. No, No, Number, Num, Sl. No, Numbered, S. Number, Sr. Number)
                    # Tightened: removed "s" and "sr" as they are not meaningful enough.
                    valid_col_0 = ["s no", "sr no", "no", "number", "num", "serial no", "serial number", "s number", "sr number", "s num", "sr num", "sno", "srno", "sl no", "slno", "numbered", "sl number", "slnumber"]
                    header0_raw = str(headers[0]).strip()
                    header0_norm = normalize(header0_raw)
                    header0_ref = f"{section_ref} - Column #1"
                    if not header0_raw:
                         errors.append({"where": header0_ref, "what": f"missing 'S. No' header: Found empty. in {redirect_title}", "suggestion": "Expected: 'S. No' or 'Sr. No'", "redirect_text": redirect_title, "severity": "medium"})
                    elif header0_norm not in valid_col_0:
                         errors.append({"where": header0_ref, "what": f"Incorrect table header: Found '{header0_raw}'. in {redirect_title}", "suggestion": "Expected: 'S. No', 'Sr. No', 'S. Number', or 'Sr. Number'", "redirect_text": redirect_title, "severity": "medium"})
                    
                    # Column 1: TEST CASE No.
                    valid_col_1 = ["test case no", "test case number", "test case num", "test case name", "test case id", "tc no", "tc number", "tc num", "tc name"]
                    header1_raw = str(headers[1]).strip()
                    header1_norm = normalize(header1_raw)
                    header1_ref = f"{section_ref} - Column #2"
                    if not header1_raw:
                         errors.append({"where": header1_ref, "what": f"missing 'TEST CASE No.' header: Found empty. in {redirect_title}", "suggestion": "Expected: 'TEST CASE No.'", "redirect_text": redirect_title, "severity": "medium"})
                    elif header1_norm not in valid_col_1:
                         errors.append({"where": header1_ref, "what": f"Incorrect table header: Found '{header1_raw}'. in {redirect_title}", "suggestion": "Expected: 'TEST CASE No.'", "redirect_text": redirect_title, "severity": "medium"})
                         
                    # Column 2: PASS FAIL
                    valid_col_2 = ["pass fail", "status", "result", "results", "pass/fail", "passfail", "result status"]
                    header2_raw = str(headers[2]).strip()
                    header2_norm = normalize(header2_raw)
                    header2_ref = f"{section_ref} - Column #3"
                    if not header2_raw:
                         errors.append({"where": header2_ref, "what": f"missing 'PASS FAIL' header: Found empty. in {redirect_title}", "suggestion": "Expected: 'PASS FAIL'", "redirect_text": redirect_title, "severity": "medium"})
                    elif header2_norm not in valid_col_2:
                         errors.append({"where": header2_ref, "what": f"Incorrect table header: Found '{header2_raw}'. in {redirect_title}", "suggestion": "Expected: 'PASS FAIL'", "redirect_text": redirect_title, "severity": "medium"})

                    # Column 3: Remarks
                    valid_col_3 = ["remarks", "remark", "observations", "observation", "comments", "comment"]
                    header3_raw = str(headers[3]).strip()
                    header3_norm = normalize(header3_raw)
                    header3_ref = f"{section_ref} - Column #4"
                    if not header3_raw:
                         errors.append({"where": header3_ref, "what": f"missing 'Remarks' header: Found empty. in {redirect_title}", "suggestion": "Expected: 'Remarks'", "redirect_text": redirect_title, "severity": "medium"})
                    elif header3_norm not in valid_col_3:
                         errors.append({"where": header3_ref, "what": f"Incorrect table header: Found '{header3_raw}'. in {redirect_title}", "suggestion": "Expected: 'Remarks'", "redirect_text": redirect_title, "severity": "medium"})

                if not rows:
                    errors.append({"where": section_ref, "what": "Table rows are missing in 'rows' field", "suggestion": "Add test result data to rows", "redirect_text": redirect_title, "severity": "high"})
                else:
                    for ridx, row in enumerate(rows, 1):
                        if len(row) < 4:
                            errors.append({"where": f"{section_ref} - Row #{ridx}", "what": f"Incomplete row data: Found {len(row)} columns. in {redirect_title}", "suggestion": "Ensure each row has 4 columns", "redirect_text": redirect_title, "severity": "medium"})
                            continue
                        
                        s_no = str(row[0]).strip()
                        tc_id = str(row[1]).strip()
                        status = str(row[2]).strip()
                        remarks = str(row[3]).strip()
                        
                        # Individual check: Expected ID is based on local Base ID + Row Index
                        expected_id = f"{base_id}.{ridx}" if base_id else f"[ID].{ridx}"
                        entry_ref = f"{section_ref} - {expected_id}"

                        # 1. S. No Check
                        if not s_no:
                            errors.append({"where": entry_ref, "what": f"S. No missing in 'S. No' column: Found empty. in {redirect_title}", "suggestion": f"Expected: '{ridx}'", "redirect_text": redirect_title, "severity": "high"})
                        elif s_no != str(ridx):
                            errors.append({"where": entry_ref, "what": f"Incorrect sequence order: Found '{s_no}'. in {redirect_title}", "suggestion": f"Expected: '{ridx}'", "redirect_text": redirect_title, "severity": "low"})

                        # 2. Test Case ID Check
                        if not tc_id:
                            errors.append({"where": entry_ref, "what": f"Test case ID missing: Found empty. in {redirect_title}", "suggestion": f"Expected: '{expected_id}'", "redirect_text": redirect_title, "severity": "high"})
                        elif tc_id != expected_id:
                            # Still check for base mismatch even if sequence is prioritized
                            is_base_mismatch = base_id and not tc_id.startswith(base_id)
                            msg_type = "Base ID mismatch" if is_base_mismatch else "Incorrect sequence order"
                                
                            errors.append({
                                "where": entry_ref, 
                                "what": f"{msg_type}: Found '{tc_id}'. in {redirect_title}", 
                                "suggestion": f"Expected: '{expected_id}'", 
                                "redirect_text": redirect_title,
                                "severity": "low"
                            })

                        # 3. Pass/Fail Status Check
                        if not status:
                            errors.append({"where": entry_ref, "what": f"Result status missing in 'PASS FAIL' column: Found empty. in {redirect_title}", "suggestion": "Expected: PASS/FAIL/NA/AVERAGE", "redirect_text": redirect_title, "severity": "high"})
                        elif status.upper() not in ["PASS", "FAIL", "NA", "AVERAGE"]:
                            errors.append({"where": entry_ref, "what": f"Invalid status: Found '{status}'. in {redirect_title}", "suggestion": "Expected: PASS, FAIL, NA, or AVERAGE", "redirect_text": redirect_title, "severity": "medium"})

                        # 4. Remarks Check
                        if not remarks or remarks in ['.', '...', ':']:
                            errors.append({"where": entry_ref, "what": f"Remarks missing or non-meaningful. in {redirect_title}", "suggestion": "Add meaningful observations", "redirect_text": redirect_title, "severity": "high"})
                    

        if errors:
            severity_priority = {"high": 0, "medium": 1, "low": 2}
            errors.sort(key=lambda x: severity_priority.get(x.get('severity', 'medium'), 1))
        return errors if errors else None

    except Exception as e:
        return [{"where": "Section 12", "what": f"Error: {e}", "severity": "high"}]

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
