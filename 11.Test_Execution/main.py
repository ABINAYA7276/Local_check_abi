import sys
import os
from pathlib import Path
import argparse
import re
import json
from typing import List, Dict, Optional

def is_meaningful_content(text: str) -> bool:
    """Check if text has meaningful content (not placeholder or empty)."""
    if not text:
        return False
    text = text.strip().lower()
    if text == 'na':
        return True
    if (text in ['none', 'n/a', 'nil', '.', '-', '_', '...'] or
        len(text) < 3 or
        all(c in '.-_,;:!? ' for c in text)):
        return False
    return True

def check_itsar_subsections(itsar_details: List[str], test_id: str) -> List[Dict]:
    definitions = {
        'a': {'label': 'a. Test Case Name', 'keywords': ['test case name', 'testcase name'], 'prefix': 'a.'},
        'b': {'label': 'b. Test Case Description', 'keywords': ['test case description', 'testcase description', 'description'], 'prefix': 'b.'},
        'c': {'label': 'c. Execution Steps', 'keywords': ['execution steps', 'execution step', 'execution'], 'prefix': 'c.'},
        'd': {'label': 'd. Test Observations', 'keywords': ['test observation', 'observation'], 'prefix': 'd.'},
        'e': {'label': 'e. Evidence Provided', 'keywords': ['evidence provided', 'evidence'], 'prefix': 'e.'},
    }
    
    sections_status = {key: {'found': False, 'has_content': False, 'label': d['label'], 'wrong_prefix': None, 'found_text': ''} for key, d in definitions.items()}
    current_section = None
    first_line = None
    
    # Preprocess: Split long concatenated strings by section markers
    expanded_details = []
    for detail in itsar_details:
        if not isinstance(detail, str): continue
        text = detail.strip()
        if not text: continue

        # Check if this is a long concatenated string with multiple sections
        # Use regex to identify section markers
        import re
        # More flexible pattern to catch variations
        pattern = r'([a-e]\.\s*(?:Test\s*Case\s*Name|Test\s*Case\s*Description|Description|Execution\s*Steps?|Test\s*Observations?|Observations?|Evidence\s*Provided|Evidence))'
        
        # Count how many section markers are in this string
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        marker_count = len(matches)
        
        if marker_count > 1:
            # This is a concatenated string, split it
            # Use regex to split by section markers while keeping them
            import re
            # More flexible pattern to catch variations
            pattern = r'([a-e]\.\s*(?:Test\s*Case\s*Name|Test\s*Case\s*Description|Description|Execution\s*Steps?|Test\s*Observations?|Observations?|Evidence\s*Provided|Evidence))'
            parts = re.split(pattern, text, flags=re.IGNORECASE)
            
            # Reconstruct by pairing markers with their content
            for i in range(len(parts)):
                part = parts[i].strip()
                if part:
                    # If this is a marker, combine it with the next part
                    if i < len(parts) - 1 and re.match(pattern, part, re.IGNORECASE):
                        combined = part + ' ' + parts[i+1].strip()
                        expanded_details.append(combined)
                    elif i == 0 or not re.match(pattern, parts[i-1], re.IGNORECASE):
                        # This is content not preceded by a marker
                        expanded_details.append(part)
        else:
            # Normal case: single line or paragraph
            expanded_details.append(text)
    
    # DEBUG PRINT removed

    for detail in expanded_details:
        if not isinstance(detail, str): continue
        text = detail.strip()
        
        # Normalize whitespace (convert NBSP, etc. to space, reduce multiple spaces)
        text_normalized = ' '.join(text.split())
        text_lower = text_normalized.lower()
        
        if not text_normalized: continue
        if first_line is None: first_line = text_normalized
        found_marker = False
        
        for key, info in definitions.items():
            if sections_status[key]['found'] and not sections_status[key]['wrong_prefix']: continue
            for kw in info['keywords']:
                # Normalized keyword
                kw_norm = ' '.join(kw.split())
                
                if kw_norm in text_lower:
                    is_header = False
                    
                    # Try regex on normalized text
                    try:
                        p_head = r'^' + re.escape(info['prefix']) + r'\s*' + re.escape(kw_norm)
                        if re.match(p_head, text_normalized, re.IGNORECASE):
                            is_header = True
                    except: pass

                    # Fallback
                    if not is_header:
                        if text_lower.startswith(info['prefix']):
                             if kw_norm in text_lower[:50]: is_header = True

                    if is_header:
                        sections_status[key]['found'] = True
                        current_section = key
                        found_marker = True
                        
                        # Content check (simplified due to normalization)
                        # Remove header prefix+kw
                        remaining = text_normalized[len(info['prefix']):].strip() # approximate
                        # Better: use regex sub on normalized
                        try:
                             p_content = r'^' + re.escape(info['prefix']) + r'\s*' + re.escape(kw_norm) + r'[:\-]?\s*'
                             remaining = re.sub(p_content, '', text_normalized, count=1, flags=re.IGNORECASE).strip()
                             if is_meaningful_content(remaining): sections_status[key]['has_content'] = True
                        except: pass
                        
                        break
            if found_marker: break
        
        if not found_marker and current_section:
            if is_meaningful_content(text):
                sections_status[current_section]['has_content'] = True
                if not sections_status[current_section]['found_text']:
                    sections_status[current_section]['found_text'] = text
                
    errors = []
    for key, status in sections_status.items():
        label = status['label']
        if not status['found']:
            why = f"Missing section: '{label}' section not found"
            if key == 'a' and first_line:
                display_line = first_line[:50] + "..." if len(first_line) > 50 else first_line
                why += f". Found: '{display_line}'" # Keep context if needed, or simplify? User wants specific format.
                # Actually, if logic found 'a' but failed strict check, maybe? 
                # Let's stick to the requested format for the main part.
            errors.append({'why': why, 'suggestion': f"Add '{label}' section", 'found': display_line if key == 'a' and first_line else None, 'label': label})
        else:
            if status['wrong_prefix']:
                why = f"Incorrect prefix: Found '{status['wrong_prefix']}' in '{label}' section"
                errors.append({'why': why, 'suggestion': f"Expected prefix: '{label}'", 'found': status['wrong_prefix'], 'label': label})
            if not status['has_content']:
                why = f"Missing content: Found empty in '{label}' section"
                errors.append({'why': why, 'suggestion': f"Add content after '{label}'", 'found': None, 'label': label})
    return errors

def check_figure_ids(itsar_details: List[str], expected_tc_number: str, test_id: str) -> List[Dict]:
    errors = []
    # Strict start matching with separator enforcement
    # Matches: "Figure 11.1.1 - Content", "Figure 11.1.1: Content"
    figure_caption_pattern = re.compile(r'^[Ff]igure\s+([\d\.]+)\s*[-–:]', re.IGNORECASE)
    found_figures = []
    figure_ids_seen = set()
    
    for detail in itsar_details:
        if not isinstance(detail, str): continue
        match = figure_caption_pattern.match(detail.strip())
        if match:
            full_id = match.group(1)
            parts = full_id.split('.')
            if len(parts) >= 2:
                # Safety check: ensure the last part is not empty before converting to int
                if parts[-1].strip():
                    suffix = int(parts[-1])
                    prefix = '.'.join(parts[:-1])
                    found_figures.append({'prefix': prefix, 'suffix': suffix, 'full_id': full_id})
                # Skip malformed figure IDs with trailing dots
            else:
                found_figures.append({'prefix': full_id, 'suffix': 0, 'full_id': full_id})
    
    expected_suffix = None
    for fig in found_figures:
        # Check alignment: Figure ID must start with the Test Case ID
        if not fig['full_id'].startswith(expected_tc_number):
            why = f"Incorrect alignment: Found '{fig['full_id']}' in Figure ID"
            suggestion = f"Expected to start with {expected_tc_number}"
            errors.append({'type': 'figure_id', 'why': why, 'suggestion': suggestion, 'found': f"Figure {fig['full_id']}"})
        else:
            # Initialize expected suffix with the first valid figure we find
            if expected_suffix is None:
                expected_suffix = fig['suffix']

            # Alignment OK, Check Sequence
            if fig['full_id'] in figure_ids_seen:
                errors.append({'type': 'figure_id', 'why': f"Duplicate ID: Found '{fig['full_id']}' in Figure ID", 'suggestion': f"Expected unique ID", 'found': f"Figure {fig['full_id']}"})
            elif fig['suffix'] != expected_suffix:
                why = f"Incorrect sequence: Found '{fig['full_id']}' in Figure ID"
                suggestion = f"Expected suffix .{expected_suffix} (e.g. {expected_tc_number}.{expected_suffix})"
                errors.append({'type': 'figure_id', 'why': why, 'suggestion': suggestion, 'found': f"Figure {fig['full_id']}"})
            else:
                # Only add to seen set and increment if the figure is valid
                figure_ids_seen.add(fig['full_id'])
                expected_suffix += 1
            
    return errors

def main():
    parser = argparse.ArgumentParser(description="Validate Section 11.")
    parser.add_argument("json_file", type=str)
    args = parser.parse_args()
    json_path = str(Path(args.json_file))
    
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')
        
    all_valid = True
    all_errors_table = []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        test_id_pattern = re.compile(r'^(\d+\.\d+\.\d+\.\d+)[:]?\s+')

        # 1. Base ID
        base_id = None
        for section in sections:
            title = section.get('title', '')
            if re.match(r'^(\d+\.\d+\.\d+):', title):
                base_id = title.split(':')[0]
                break
            if section.get('section_id') == 'SEC-02' or re.search(r'2\.\s+Security Requirement', title, re.IGNORECASE):
                for item in section.get('content', []):
                    text = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                    m = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                    if m: 
                        base_id = m.group(1)
                        break
                if base_id: break

        # 2. Identify Section 11 Range & Content
        in_section_11 = False
        section11_found = False
        section11_found_via_header = False  # Track if proper main header was found
        section11_id = None
        section11_title_error = None
        
        found_test_ids = []
        found_test_case_numbers = []
        current_test_case_number = None

        for section in sections:
            title = section.get('title', '').strip()
            level = section.get('level', 0)
            sec_id = section.get('section_id', 'Unknown')
            
            # Start of Section 11 (Main Header)
            # Check strictly for "11." OR loosely for "Test Execution" keyword to catch typos like "10. Test Execut:"
            # BUT ensure it starts with 10 or 11 to avoid false positives like "8.4 Test Execution"
            is_sec_11_candidate = re.match(r'^11\.\s+Test\s+Execution', title, re.IGNORECASE)
            title_lower = title.lower()
            keyword_match = "test execution" in title_lower or "test execut" in title_lower
            starts_with_10_11 = re.match(r'^(10|11)\.', title)
            
            if is_sec_11_candidate or (keyword_match and starts_with_10_11 and not in_section_11):
                in_section_11 = True
                section11_found = True
                section11_found_via_header = True  # Found via proper main header
                section11_id = sec_id
                
                # Title Validation
                # Expected: "11. Test Execution:"
                if not re.match(r'^11\.\s+Test\s+Execution:?$', title, re.IGNORECASE):
                     section11_title_error = {
                        'where': "Section 11 - 11. Test Execution:",
                        'what': f"Incorrect Title: '{title}'",
                        'suggestion': "Expected: '11. Test Execution:'",
                        'description': "The section title must be exactly '11. Test Execution:'.",
                        'redirect_text': title
                     }
                continue
            
            # End of Section 11 (Next main section)
            # Stop at 12 or 10, or any other main section that isn't 11
            # Handle cases like "12. " or "12 " 
            if re.match(r'^(12|10|13)(\.|\s)', title) and in_section_11: 
                 in_section_11 = False
                 continue # Ensure we don't process this line further
            
            # Also safety check: if we see "Test Case Result" (Section 12 keyword)
            if "test case result" in title.lower() and re.match(r'^12', title):
                in_section_11 = False
                continue
            
            # Additional Start Trigger: If we see 11.X and we aren't in Section 11 yet (missing main header case)
            if re.match(r'^11\.', title) and not in_section_11:
                # Assuming implicit start logic if the main header was missing
                in_section_11 = True
                # We don't verify title here because we found a subsection, not the main section.
                # Main section missing error will be handled by `section11_found` check later.

            if not in_section_11:
                continue

            # Process Section 11 Content
            
            # Subsection: 11.1 Test Case Number
            if re.match(r'^11\.\d+', title):
                 # Extract subsection number
                 parts = title.split(' ', 1)
                 num = parts[0].strip(':')
                 
                 # Check if it has the correct keyword and format
                 has_keyword = "test case number" in title.lower()
                 is_correct = "Test Case Number" in (parts[1] if len(parts)>1 else "")
                 
                 # Add to list regardless of format (so we can validate it later)
                 found_test_case_numbers.append({'number': num, 'title': title, 'is_correct_format': is_correct, 'section_id': sec_id})
                 current_test_case_number = num
                 section11_found = True # Count as found
 
                 # Always check embedded content for Test IDs (even if title format is wrong)
                 content_list = []
                 if 'content' in section:
                     for item in section['content']:
                         t = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                         content_list.append(t)
                         m = test_id_pattern.match(t)
                         if m:
                             found_test_ids.append({'id': m.group(1), 'title': t, 'section_id': sec_id, 'section': section, 'test_case_number': num, 'is_embedded': True, 'content_list': content_list})
                 continue

            # Test ID Section
            if re.search(r'^\d+\.\d+\.\d+\.\d+', title):
                 match = test_id_pattern.match(title)
                 if match or "itsar" in title.lower():
                    tid = match.group(1) if match else title.split(' ')[0]
                    # STRICT FILTER to avoid overlap if logic failed: Must start with 11. or BaseID
                    # Wait, if `in_section_11` is true, we are safe. 
                    # But double check:
                    if tid.startswith('12.') or tid.startswith('10.'): continue 
                    
                    found_test_ids.append({'id': tid, 'title': title, 'section_id': sec_id, 'section': section, 'test_case_number': current_test_case_number, 'is_embedded': False, 'content_list': None})
                    section11_found = True

        # Validation Logic
        if not section11_found and not found_test_ids:
             all_valid = False
             all_errors_table.append({'where': "Section 11", 'what': "Section 11 Missing", 'suggestion': "Add Section 11", 'redirect_text': "Section 11 Missing"})
        else:
            if section11_title_error:
                all_valid = False
                all_errors_table.append(section11_title_error)
            
            # Check if subsections exist but main header is missing or incorrect
            if not section11_found_via_header and (found_test_case_numbers or found_test_ids):
                all_valid = False
                all_errors_table.append({
                    'where': "Section 11 - 11. Test Execution:",
                    'what': "Missing or Incorrect Section 11 Main Header",
                    'suggestion': "Expected: '11. Test Execution:'",
                    'redirect_text': "Section 11"
                })
            
            # Check subsections
            for i, tc in enumerate(found_test_case_numbers, 1):
                num = tc['number']
                l2_exp, l3_exp = f"11.{i}", f"11.1.{i}"
                if num != l2_exp and num != l3_exp:
                    if not num.startswith("11."):
                        all_valid=False
                        all_errors_table.append({'where': f"Subsection {l2_exp} - Test Case Number:", 'what': f"Incorrect Base: Found '{num}'", 'suggestion': f"Expected {l2_exp}", 'redirect_text': f"{tc['title']}"})
                    else:
                        all_valid=False
                        all_errors_table.append({'where': f"Subsection {l2_exp} - Test Case Number:", 'what': f"Incorrect sequence order: Found '{num}' in section 11", 'suggestion': f"Expected {l2_exp}", 'redirect_text': f"{tc['title']}"})
                
                # Check title format
                if not tc.get('is_correct_format', True):
                    all_valid=False
                    all_errors_table.append({'where': f"Subsection {num} - Test Case Number:", 'what': f"Incorrect title format: Found '{tc['title']}'", 'suggestion': f"Expected '{num} Test Case Number:'", 'redirect_text': f"{tc['title']}"})
            
            # Create map for Subsection Titles for redirection
            tc_title_map = {tc['number']: tc['title'] for tc in found_test_case_numbers}

            # Check Test IDs
            for i, test in enumerate(found_test_ids, 1):
                tid = test['id']
                sec_id = test['section_id']
                title = test['title']
                tc_num = test.get('test_case_number')
                
                # Calculate expected ID
                if base_id:
                    exp_id = f"{base_id}.{i}"
                else:
                    # Build expected ID by replacing the last part with i
                    parts = tid.split('.')
                    exp_id = '.'.join(parts[:-1] + [str(i)]) if len(parts) >= 4 else tid
                
                # Construct 'where' location using EXPECTED ID (not found error)
                # Example: "Section 11 - 11.2 - 1.1.1.2  ITSAR WiFi-CPE" (expected, not 1.1.1.9)
                expected_title = title.replace(tid, exp_id) if tid in title else title
                identifier = expected_title.strip() if title else exp_id
                where_val = f"Section 11 - {tc_num} - {identifier}" if tc_num else f"Section 11 - {identifier}"
                
                # Use Subsection Title for redirect text if available ("11.1 Test Case Number:")
                # Otherwise fall back to ID
                subsection_title = tc_title_map.get(tc_num)
                redirect_val = subsection_title if subsection_title else tid

                # Base ID / Sequence Check
                if base_id:
                     parts = tid.split('.')
                     base_match = '.'.join(parts[:3]) == base_id if len(parts)>=3 else False
                     if not base_match:
                         all_valid=False
                         all_errors_table.append({'where': where_val, 'what': f"Base ID Mismatch: {tid}", 'suggestion': f"Expected base {base_id}", 'redirect_text': redirect_val})
                     elif tid != exp_id:
                         all_valid=False
                         all_errors_table.append({'where': where_val, 'what': f"Sequence Mismatch: {tid}", 'suggestion': f"Expected {exp_id}", 'redirect_text': redirect_val})
                else:
                     # Even without base_id, check if the suffix matches expected sequence
                     parts = tid.split('.')
                     if len(parts) >= 4 and parts[-1].strip():
                         suffix = int(parts[-1])
                         if suffix != i:
                             all_valid=False
                             # Build expected ID by replacing the last part with i
                             expected_tid = '.'.join(parts[:-1] + [str(i)])
                             all_errors_table.append({'where': where_val, 'what': f"Sequence Mismatch: Found '{tid}'", 'suggestion': f"Expected '{expected_tid}'", 'redirect_text': redirect_val})
                
                # Validate Test ID format: must contain "ITSAR" and "WiFi-CPE" (semantic check, case-insensitive)
                if title and tid in title:
                    # Extract the text after the Test ID
                    remaining_text = title.split(tid, 1)[1].strip().strip(':').strip() if tid in title else ""
                    # Check if it contains the required keywords (case-insensitive, flexible spacing)
                    remaining_lower = remaining_text.lower().replace('-', ' ').replace('  ', ' ')
                    if remaining_text and not ("itsar" in remaining_lower and "wifi" in remaining_lower and "cpe" in remaining_lower):
                        all_valid = False
                        all_errors_table.append({'where': where_val, 'what': f"Invalid format: Found '{title}'", 'suggestion': f"Expected format: '{exp_id} ITSAR WiFi-CPE'", 'redirect_text': redirect_val})
                
                # Content Check
                content = []
                if test['is_embedded']:
                     content = test['content_list']
                else:
                    if 'itsar_section_details' in test['section']: content = test['section']['itsar_section_details']
                    elif 'content' in test['section']:
                         for it in test['section']['content']:
                             content.append(it.get('text', '') if isinstance(it, dict) else str(it))
                    if 'security_requirement' in test['section']:
                        content.append(test['section']['security_requirement'])
                
                if not content:
                    all_valid = False
                    all_errors_table.append({'where': where_val, 'what': f"Content missing (empty)", 'suggestion': "Add test case content", 'redirect_text': redirect_val})
                else:
                    sub_err = check_itsar_subsections(content, tid)
                    for err in sub_err:
                        all_valid = False
                        all_errors_table.append({'where': where_val, 'what': err['why'], 'suggestion': err['suggestion'], 'redirect_text': redirect_val})
                        
                    # Figure check
                    # Use the actual test case number found (e.g. 11.3 or 11.1.3) for alignment expectation
                    expected_num = test.get('test_case_number')
                    if not expected_num: expected_num = f"11.1.{i}" # Fallback
                    
                    fig_err = check_figure_ids(content, expected_num, tid)
                    for err in fig_err:
                        all_valid=False
                        all_errors_table.append({'where': where_val, 'what': err['why'], 'suggestion': err['suggestion'], 'redirect_text': redirect_val})

    except Exception as e:
        print(json.dumps([{"where": "Process Error", "what": str(e), "suggestion": "Fix JSON", "redirect_text": "Error"}], indent=4))
        sys.exit(1)

    # Output
    findings = []
    for e in all_errors_table:
        findings.append({
            "where": e['where'], 
            "what": e['what'], 
            "suggestion": e['suggestion'], 
            "redirect_text": e['redirect_text']
        })
    
    try:
        with open('output.json', 'w', encoding='utf-8') as f: json.dump(findings, f, indent=4)
    except: pass
    
    # Always print output to console
    print(json.dumps(findings, indent=4))
    sys.exit(1 if not all_valid else 0)

if __name__ == "__main__":
    main()
