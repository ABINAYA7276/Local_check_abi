import sys
import os
from pathlib import Path
import argparse
import re
import json
from typing import List, Dict, Optional

def is_meaningful_content(text: str) -> bool:
    """Check if text has meaningful content (not placeholder or empty)."""
    if not text or not isinstance(text, str):
        return False
    cleaned = text.strip()
    # Remove common labels GLOBALLY to see if there is actual content
    temp = re.sub(r'Test\s*Sc[eh]n?ario\s*[:.-]*', '', cleaned, flags=re.IGNORECASE).strip()
    temp = re.sub(r'Test\s*Case\s+Number\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()
    temp = re.sub(r'[a-e]\.\s*(Test\s*Case\s*Name|TestCaseName|Test\s*Case\s*Description|TestCaseDescription|Execution\s*Steps|ExecutionSteps|Test\s*Observations|TestObservations|Evidence\s*Provided|EvidenceProvided|Description)\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()
    temp = re.sub(r'TC\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()

    if not temp or temp.lower() in [".", ":", "-", "_", "...", "n/a", "none", "nil"]:
        return False
    if not re.search(r'\w', temp):
        return False
    return True

def check_itsar_subsections(itsar_details: List[str], test_id: str) -> List[Dict]:
    definitions = {
        'a': {'label': 'a. Test Case Name', 'keywords': ['test case name', 'testcase name', 'testcasename'], 'prefix': 'a.'},
        'b': {'label': 'b. Test Case Description', 'keywords': ['test case description', 'testcase description', 'testcasedescription', 'description'], 'prefix': 'b.'},
        'c': {'label': 'c. Execution Steps', 'keywords': ['execution steps', 'execution step', 'executionsteps', 'execution'], 'prefix': 'c.'},
        'd': {'label': 'd. Test Observations', 'keywords': ['test observation', 'testobservation', 'observation'], 'prefix': 'd.'},
        'e': {'label': 'e. Evidence Provided', 'keywords': ['evidence provided', 'evidenceprovided', 'evidence'], 'prefix': 'e.'},
    }
    
    sections_status = {key: {'found': False, 'has_content': False, 'label': d['label'], 'wrong_prefix': None, 'found_text': '', 'intended_header': None} for key, d in definitions.items()}
    current_section = None
    first_line = None
    
    # Preprocess: Split long concatenated strings by section markers
    expanded_details = []
    # More flexible pattern to catch variations
    pattern = r'([a-e]\.\s*(?:Test\s*Case\s*Name|Test\s*Case\s*Description|Description|Execution\s*Steps?|Test\s*Observations?|Observations?|Evidence\s*Provided|Evidence))'
    
    for detail in itsar_details:
        if not isinstance(detail, str): continue
        text = detail.strip()
        if not text: continue

        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        marker_count = len(matches)
        
        if marker_count > 1:
            parts = re.split(pattern, text, flags=re.IGNORECASE)
            # Reconstruct by pairing markers with their content
            for i in range(len(parts)):
                part = parts[i].strip()
                if part:
                    if i < len(parts) - 1 and re.match(pattern, part, re.IGNORECASE):
                        combined = part + ' ' + parts[i+1].strip()
                        expanded_details.append(combined)
                    elif i == 0 or not re.match(pattern, parts[i-1], re.IGNORECASE):
                        expanded_details.append(part)
        else:
            expanded_details.append(text)
    
    for detail in expanded_details:
        if not isinstance(detail, str): continue
        text = detail.strip()
        text_normalized = ' '.join(text.split())
        text_lower = text_normalized.lower()
        
        if not text_normalized: continue
        if first_line is None: first_line = text_normalized
        found_marker = False
        
        for key, info in definitions.items():
            if sections_status[key]['found'] and not sections_status[key]['wrong_prefix']: continue
            
            # Check for keyword matches
            found_kw = False
            for kw in info['keywords']:
                kw_norm = ' '.join(kw.split())
                if kw_norm in text_lower:
                    is_header = False
                    p_head = r'^' + re.escape(info['prefix']) + r'\s*' + re.escape(kw_norm)
                    if re.match(p_head, text_normalized, re.IGNORECASE):
                        is_header = True
                    if not is_header:
                        if text_lower.startswith(info['prefix']):
                             if kw_norm in text_lower[:50]: is_header = True

                    if is_header:
                        sections_status[key]['found'] = True
                        sections_status[key]['intended_header'] = None
                        current_section = key
                        found_marker = True
                        found_kw = True

                        # Check for missing spaces or exact format mismatch
                        actual_label_part = text_normalized.split(':')[0].strip()
                        if actual_label_part.lower() != info['label'].lower():
                             # It matched enough to be 'found', but formatting is wrong
                             sections_status[key]['format_error'] = True
                             sections_status[key]['found_header'] = text_normalized

                        p_content = r'^' + re.escape(info['prefix']) + r'\s*' + re.escape(kw_norm) + r'[:\-]?\s*'
                        remaining = re.sub(p_content, '', text_normalized, count=1, flags=re.IGNORECASE).strip()
                        if is_meaningful_content(remaining): sections_status[key]['has_content'] = True
                        break
                    else:
                        if re.match(r'^[\d\w\.]+\s*' + re.escape(kw_norm), text_normalized, re.IGNORECASE):
                            sections_status[key]['found'] = True
                            sections_status[key]['wrong_prefix'] = text_normalized
                            current_section = key
                            found_marker = True
                            found_kw = True
                            p_any_prefix = r'^.*?'+re.escape(kw_norm)+r'[:\-]?\s*'
                            remaining = re.sub(p_any_prefix, '', text_normalized, count=1, flags=re.IGNORECASE).strip()
                            if is_meaningful_content(remaining): sections_status[key]['has_content'] = True
                            break
            
            if not found_kw:
                # Potential header match by prefix alone (for reporting typos)
                if text_lower.startswith(info['prefix']) and not sections_status[key]['found']:
                    if not sections_status[key]['intended_header']:
                        sections_status[key]['intended_header'] = text_normalized
            
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
            intended = status.get('intended_header')
            if intended:
                why = f"Incorrect header format: Found '{intended}'"
                suggestion = f"Expected: '{label}:'"
                sev = 'Medium'
            else:
                why = f"Missing section: '{label}' section not found"
                if first_line:
                    display_line = first_line[:50] + "..." if len(first_line) > 50 else first_line
                    why += f". Found: '{display_line}'"
                suggestion = f"Add '{label}' section"
                sev = 'High'
            
            errors.append({
                'why': why, 
                'suggestion': suggestion, 
                'label': label,
                'severity': sev
            })
        else:
            if status['wrong_prefix']:
                why = f"Incorrect prefix: Found '{status['wrong_prefix']}'"
                errors.append({
                    'why': why, 
                    'suggestion': f"Expected: '{label}:'", 
                    'label': label,
                    'severity': 'Medium'
                })
            
            # Check for space/format error (a, b, c, d, e)
            if status.get('format_error'):
                 errors.append({
                    'why': f"Incorrect header format: Found '{status['found_header'].split(':')[0].strip()}'",
                    'suggestion': f"Expected: '{label}:'",
                    'label': label,
                    'severity': 'Low'
                })

            if not status['has_content']:
                why = f"Missing content: Found empty in '{label}' section"
                errors.append({
                    'why': why, 
                    'suggestion': f"Add content after '{label}'", 
                    'label': label,
                    'severity': 'High'
                })
    return errors

def check_figure_ids(items: List, expected_tc_number: str, test_id: str) -> List[Dict]:
    errors = []
    # Match primary captions like "Figure 11.1.1.1 - Title"
    # Separator check: should have a separator (hyphen preferred)
    figure_caption_pattern = re.compile(r'^[Ff]igure\s+([\d\.]+)\s*([-–: ])\s*(.*)$', re.IGNORECASE)
    
    found_figures = [] # List of dicts
    
    current_label = "General Section"
    img_counter = 0
    label_img_counts = {}

    # Pass 1: Identification & Image-to-Caption linkage
    for i, item in enumerate(items):
        if isinstance(item, str):
            # Identify subsection headers to provide context
            if re.match(r'^[a-e]\.\s+', item, re.IGNORECASE):
                current_label = item.split(':')[0].strip()
                img_counter = 0 # Reset counter for new label
            continue

        if isinstance(item, dict) and item.get('type') == 'image':
            img_counter += 1
            ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(img_counter, f"{img_counter}th")
            context_where = f"under {current_label} ({ordinal} image)"
            
            # Check if an image is followed by a caption
            has_caption = False
            for j in range(i + 1, len(items)):
                next_item = items[j]
                if not isinstance(next_item, str): continue
                text = next_item.strip()
                if not text: continue
                
                if figure_caption_pattern.match(text):
                    has_caption = True
                    break
                else:
                    # Found text but it's not a caption
                    break
            
            if not has_caption:
                errors.append({
                    'type': 'figure_missing', 
                    'why': f"Caption missing: Found {context_where}", 
                    'suggestion': f"Expected: 'Figure {expected_tc_number}.X: description' immediately after the image", 
                    'severity': 'Medium'
                })

    # Pass 2: Captions validation (sequence, format, alignment)
    for item in items:
        if not isinstance(item, str): continue
        text = item.strip()
        cap_match = figure_caption_pattern.match(text)
        if cap_match:
            full_id = cap_match.group(1).strip('.')
            sep = cap_match.group(2)
            figure_title = cap_match.group(3).strip()
            parts = full_id.split('.')
            
            fig_data = {
                'full_id': full_id, 
                'title': figure_title,
                'sep': sep,
                'suffix': int(parts[-1]) if parts[-1].isdigit() else 0,
                'text': text
            }
            found_figures.append(fig_data)
            
            # (Separator check removed - normalized as requested)
    
    # Sequential checks
    expected_suffix = 1
    for i, fig in enumerate(found_figures, 1):
        actual_id = fig['full_id']
        correct_id = f"{expected_tc_number}.{expected_suffix}"
        
        # 1. Alignment Check
        if not actual_id.startswith(expected_tc_number):
            errors.append({
                'type': 'figure_id', 
                'why': f"Incorrect Figure ID alignment: Found 'Figure {actual_id}'", 
                'suggestion': f"Expected to start with '{expected_tc_number}' (e.g. Figure {correct_id})", 
                'severity': 'Low'
            })
        # 2. Sequence Check
        elif fig['suffix'] != expected_suffix:
            errors.append({
                'type': 'figure_id', 
                'why': f"Incorrect Figure ID sequence: Found '{fig['text']}'", 
                'suggestion': f"Expected Figure {correct_id}", 
                'severity': 'Low'
            })
            
        # 3. Title Check
        if not is_meaningful_content(fig['title']):
            errors.append({
                'type': 'figure_title', 
                'why': f"Figure title missing: Found '{fig['title']}' for Figure {actual_id}", 
                'suggestion': f"Add a descriptive title for Figure {actual_id}", 
                'severity': 'Medium'
            })
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
        test_id_pattern = re.compile(r'\b(\d+\.\d+\.\d+\.\d+)\b')
        test_id_relaxed  = re.compile(r'^(\d+\.\d+\.\d+\.\d+)')  # no word-boundary — catches '1.1.2.6ITSAR'

        # Enhanced Base ID extraction logic
        base_id = None
        
        # 1. Check Document Name
        doc_name = data.get('document', '')
        m_doc = re.search(r'(\d+\.\d+\.\d+)', doc_name)
        if m_doc: 
            base_id = m_doc.group(1)
            
        # 2. Check Frontpage Data
        if not base_id:
            fp_content = data.get('frontpage_data', {}).get('content', [])
            for line in fp_content:
                if not isinstance(line, str): continue
                m_fp = re.search(r'(\d+\.\d+\.\d+)', line)
                if m_fp:
                    base_id = m_fp.group(1)
                    break

        # 3. Check Section 2 or fallback
        if not base_id:
            for section in sections:
                title = section.get('title', '').strip()
                
                is_req_sec = "Security Requirement No & Name" in title or re.search(r'^2\.', title) or re.search(r'Security\s+Requirement', title, re.IGNORECASE)
                # Check field
                req_text = section.get('security_requirement', '')
                m = re.search(r'(\d+\.\d+\.\d+)', req_text)
                if m:
                    base_id = m.group(1).strip()
                    break
                # Check content
                for it in section.get('content', []):
                    text = it.get('text', '').strip() if isinstance(it, dict) else str(it).strip()
                    m = re.search(r'(\d+\.\d+\.\d+)', text)
                    if m:
                        base_id = m.group(1).strip()
                        break
                if base_id: break

        # IDENTIFICATION SUCCESSFUL
        target_section = None
        found_title = ""
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            # Relaxed identification: strictly require 'test' and 'execution'
            if "test" in title_lower and "execution" in title_lower:
                 target_section = section
                 found_title = title
                 # If it also contains '11', it's highly likely the correct one.
                 if "11" in title_lower: break
        
        if not target_section:
             print(json.dumps([{
                "where": "11. Test Execution:",
                "what": "Section 11 missing",
                "suggestion": "Expected: '11. Test Execution:'",
                "redirect_text": "Test Execution",
                "severity": "High"
            }], indent=4))
             sys.exit(0)

        # 1. TITLE VALIDATION
        title_lower = found_title.lower()
        has_body = "test" in title_lower and "execution" in title_lower
        
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("11.")

        if not (has_correct_num and has_body):
            if has_body and has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = num_prefix_match.group(1).strip()
                all_errors_table.append({
                    "sort_key": 5,
                    "where": "11. Test Execution:",
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '11.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '11.'. Expected: '11. Test Execution:'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_body and not has_any_number:
                # Title body is correct but section number "11." is missing entirely
                all_errors_table.append({
                    "sort_key": 5,
                    "where": "11. Test Execution:",
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": "Add the section number prefix. Expected: '11. Test Execution:'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })
            else:
                # Title is entirely wrong or absent
                print(json.dumps([{
                    "where": "11. Test Execution:",
                    "what": "Section 11 missing",
                    "suggestion": "Expected: '11. Test Execution:'",
                    "redirect_text": found_title,
                    "severity": "High"
                }], indent=4))
                sys.exit(0)
            # proceed to content check if we have the body
            
        in_section_11 = False
        section11_found = True # Since we found it above
        current_test_case_number = None
        found_test_case_numbers = []
        found_test_ids = []

        for section in sections:
            title = section.get('title', '').strip()
            # Reuse the finding logic to start inside Section 11
            if section == target_section:
                in_section_11 = True
                continue
            
            if in_section_11 and re.match(r'^(12|10|13)(\.|\s)', title):
                 in_section_11 = False
                 continue

            if re.match(r'^11\.', title) and not in_section_11:
                in_section_11 = True

            if not in_section_11: continue

            if re.match(r'^11\.', title):
                 # Handle list title
                 if isinstance(title, list):
                     title_text = " ".join([str(i) for i in title if i]).strip()
                 else:
                     title_text = str(title).strip()
                     
                 match_num = re.match(r'^(11[\d\s\.]+)', title_text)
                 num = match_num.group(1).replace(' ', '').strip(':').strip('.') if match_num else title_text.split(' ', 1)[0].replace(' ', '').strip(':').strip('.')
                 is_correct = "Test Case Number:" in title_text
                 found_test_case_numbers.append({'number': num, 'title': title_text, 'is_correct_format': is_correct})
                 current_test_case_number = num
                 section11_found = True
                 content_list = []
                 
                 raw_content = section.get('content', [])
                 items = raw_content if isinstance(raw_content, list) else [raw_content]
                 for item in items:
                      if isinstance(item, dict) and item.get('type') == 'image':
                           content_list.append({'type': 'image', 'path': item.get('image_path')})
                           continue

                      t = ""
                      if isinstance(item, dict):
                          t = item.get('text', '')
                      elif isinstance(item, list):
                          t = " ".join([str(i) for i in item if i])
                      else:
                          t = str(item)
                      
                      t = t.strip()
                      if not t: continue
                      content_list.append(t)
                      
                      m = test_id_pattern.match(t)
                      m_relax = test_id_relaxed.match(t) if not m else None
                      if m:
                          found_test_ids.append({'id': m.group(1), 'title': t, 'section': section, 'test_case_number': num, 'is_embedded': True, 'content_list': content_list, 'missing_space': False})
                      elif m_relax:
                          extracted_id = m_relax.group(1)
                          # Dynamically derive expected suffix from text after the ID (not hardcoded)
                          raw_after = t[len(extracted_id):].strip().lstrip(':- ')
                          exp_suffix = raw_after if raw_after else 'ITSAR WiFi-CPE'
                          all_errors_table.append({
                              'sort_key': int(num.split('.')[-1]) * 1000 + 49 if num and num.split('.')[-1].isdigit() else 9999,
                              'where': f'11. Test Execution - Test Case Number {num} - Test Case {extracted_id}',
                              'what': f"Incorrect format: Missing space after ID in '{t}'",
                              'suggestion': f"Expected: '{extracted_id} {exp_suffix}'",
                              'redirect_text': num,
                              'severity': 'Low'
                          })
                          all_valid = False
                          found_test_ids.append({'id': extracted_id, 'title': t, 'section': section, 'test_case_number': num, 'is_embedded': True, 'content_list': content_list, 'missing_space': True})
                 continue

            if re.search(r'^\d+\.\d+\.\d+\.\d+', title):
                 # Handle list title
                 if isinstance(title, list):
                     title_text = " ".join([str(i) for i in title if i]).strip()
                 else:
                     title_text = str(title).strip()
                     
                 match = test_id_pattern.match(title_text)
                 if match or "itsar" in title_text.lower():
                    tid = match.group(1) if match else title_text.split(' ')[0]
                    if tid.startswith('12.') or tid.startswith('10.'): continue 
                    found_test_ids.append({'id': tid, 'title': title_text, 'section': section, 'test_case_number': current_test_case_number, 'is_embedded': False, 'content_list': None})
                    section11_found = True

        if not section11_found:
             all_errors_table.append({'sort_key': 0, 'where': "Test Execution", 'what': "Section 11 Missing", 'suggestion': "Add Section 11", 'redirect_text': "Section 11 Missing", 'severity': 'High'})
        else:
            if all_errors_table: all_valid = False
            
            base_suffix = base_id.split('.')[-1] if base_id and '.' in base_id else "1"
            # Determine Subsection Prefix Pattern (11.i vs 11.x.i)
            sub_prefix_base = "11"
            if found_test_case_numbers:
                first_tc = found_test_case_numbers[0]['number']
                parts = first_tc.split('.')
                if len(parts) >= 2 and parts[0] == "11":
                    # Pattern is 11.x...i
                    sub_prefix_base = ".".join(parts[:-1])

            for i, tc in enumerate(found_test_case_numbers, 1):
                num = tc['number']
                l3_exp = f"{sub_prefix_base}.{i}"
                where_sub = f"11. Test Execution - Subsection {l3_exp}"
                sort_val = i * 1000  # Base sort key for this TC index
                
                # Check format "ID Test Case Number:"
                expected_title = f"{l3_exp} Test Case Number:"
                actual_title = tc['title'].strip()
                
                # Consolidated Format Check
                actual_clean = " ".join(actual_title.split()).strip()
                
                if actual_clean != expected_title:
                    # Case 1: Sequence/ID error
                    if num != l3_exp:
                        all_errors_table.append({
                            'sort_key': sort_val,
                            'where': where_sub, 
                            'what': f"Incorrect sequence/base: Found '{num}' instead of '{l3_exp}'", 
                            'suggestion': f"Expected: '{expected_title}'", 
                            'redirect_text': f"{tc['title']}", 
                            'severity': 'Low'
                        })
                    # Case 2: Missing space (ID is immediately followed by something other than space, colon, or hyphen)
                    elif re.match(r'^' + re.escape(l3_exp) + r'[^\s:\-–]', actual_title):
                        all_errors_table.append({
                            'sort_key': sort_val,
                            'where': where_sub, 
                            'what': f"Incorrect format: Missing space after ID in '{actual_title}'", 
                            'suggestion': f"Expected: '{expected_title}'", 
                            'redirect_text': f"{tc['title']}", 
                            'severity': 'Low'
                        })
                    # Case 3: Other format issues (Text content mismatch)
                    else:
                        all_errors_table.append({
                            'sort_key': sort_val,
                            'where': where_sub, 
                            'what': f"Incorrect title format: Found '{actual_clean}'", 
                            'suggestion': f"Expected: '{expected_title}'", 
                            'redirect_text': f"{tc['title']}", 
                            'severity': 'Medium'
                        })
                    all_valid = False
                elif actual_title != expected_title:
                    # Cleaned matches but original has spacing issues
                    # Check specifically for NO space/separator after ID
                    if re.match(r'^' + re.escape(l3_exp) + r'[^\s:\-–]', actual_title):
                        all_errors_table.append({
                            'sort_key': sort_val,
                            'where': where_sub, 
                            'what': f"Incorrect format: Missing space after ID in '{actual_title}'", 
                            'suggestion': f"Expected: '{expected_title}'", 
                            'redirect_text': f"{tc['title']}", 
                            'severity': 'Low'
                        })
                        all_valid = False
            
            # Create a lookup for expected subsection IDs
            tc_expected_map = {tc['number']: f"{sub_prefix_base}.{idx}" for idx, tc in enumerate(found_test_case_numbers, 1)}
            tc_title_map = {tc['number']: tc['title'] for tc in found_test_case_numbers}
            for i, test in enumerate(found_test_ids, 1):
                tid = test['id']
                tc_num = test.get('test_case_number')
                # Derive expected ID from test ID's own suffix to avoid
                # false positives caused by formatting issues (e.g. missing
                # spaces) in earlier test cases that may shift the counter.
                if base_id and tid:
                    tid_parts = tid.split('.')
                    if len(tid_parts) >= 4 and ".".join(tid_parts[:3]) == base_id:
                        # Use the actual suffix from the found ID to compute expected
                        exp_id = tid  # Correct if base matches
                    else:
                        exp_id = f"{base_id}.{i}" if base_id else tid
                else:
                    exp_id = f"{base_id}.{i}" if base_id else tid
                
                # Find the CORRECT expected subsection suffix
                expected_sub_prefix = tc_expected_map.get(tc_num, tc_num)
                
                # New descriptive 'where' field using the EXPECTED number for location clarity
                where_val = f"11. Test Execution - Test Case Number {expected_sub_prefix} - Test Case {exp_id}"
                redirect_val = tc_title_map.get(tc_num, tid)
                sort_val = i * 1000 + 50 # Ensure it comes after the header check for the same index

                # 1. Base ID Check
                is_base_mismatch = False
                if base_id and tid:
                    found_parts = tid.split('.')
                    if len(found_parts) >= 3:
                        if ".".join(found_parts[:3]) != base_id:
                            is_base_mismatch = True
                
                if is_base_mismatch:
                    all_errors_table.append({
                        'sort_key': sort_val,
                        'where': where_val, 
                        'what': f"Base ID mismatch: Found '{tid}'. expected prefix '{base_id}'.", 
                        'suggestion': f"Ensure Base ID is {base_id}", 
                        'redirect_text': redirect_val, 
                        'severity': 'Low'
                    })
                    all_valid = False

                # 2. Sequence Check
                # Now that the relaxed regex captures IDs like '1.1.2.6ITSAR',
                # the counter 'i' is accurate. Restore full sequence check.
                exp_id = f"{base_id}.{i}" if base_id else tid
                if not is_base_mismatch and tid != exp_id:
                    all_errors_table.append({
                        'sort_key': sort_val + 1,
                        'where': where_val,
                        'what': f"Incorrect sequence: Found '{tid}' instead of '{exp_id}'",
                        'suggestion': f"Fix ID to {exp_id}",
                        'redirect_text': redirect_val,
                        'severity': 'Low'
                    })
                    all_valid = False
                
                # 3. Label Check "ITSAR WiFi-CPE"
                expected_title_suffix = "ITSAR WiFi-CPE"
                actual_test_title = test['title'].strip()
                
                # Check for space after ID: skip if already flagged by relaxed match (avoid duplicate)
                if not test.get('missing_space', False) and tid in actual_test_title and not re.match(r'^' + re.escape(tid) + r'[:\-–\s]', actual_test_title):
                    all_errors_table.append({
                        'sort_key': sort_val + 1.5,
                        'where': where_val, 
                        'what': f"Incorrect format: Missing space after ID in '{actual_test_title}'", 
                        'suggestion': f"Expected: '{tid} {expected_title_suffix}'", 
                        'redirect_text': redirect_val, 
                        'severity': 'Low'
                    })
                    all_valid = False

                if tid in actual_test_title:
                    rem = actual_test_title.split(tid, 1)[1].strip()
                    if expected_title_suffix.lower() not in rem.lower():
                        all_errors_table.append({
                            'sort_key': sort_val + 2,
                            'where': where_val, 
                            'what': f"Incorrect Title suffix: Found '{rem}' instead of '{expected_title_suffix}'", 
                            'suggestion': f"Expected format: '{exp_id} {expected_title_suffix}'", 
                            'redirect_text': redirect_val, 
                            'severity': 'Medium'
                        })
                        all_valid = False

                # 4. Content Validation
                content = []
                if test['is_embedded']: 
                    content = test['content_list']
                else: 
                    # Aggregate content from itsar_section_details and content fields
                    for field_name in ['itsar_section_details', 'content']:
                        field_val = test['section'].get(field_name, [])
                        items = field_val if isinstance(field_val, list) else [field_val]
                        for it in items:
                            if isinstance(it, dict) and it.get('type') == 'image':
                                content.append({'type': 'image', 'path': it.get('image_path')})
                                continue
                            
                            text = ""
                            if isinstance(it, dict):
                                text = it.get('text', '')
                            elif isinstance(it, list):
                                text = " ".join([str(v) for v in it if v])
                            else:
                                text = str(it)
                            if text.strip():
                                content.append(text.strip())
                
                text_only_content = [c for c in content if isinstance(c, str)]
                if not content or not any(is_meaningful_content(c) for c in text_only_content):
                    all_errors_table.append({
                        'sort_key': sort_val + 3,
                        'where': where_val, 
                        'what': "Content missing: Test case details are missing or empty", 
                        'suggestion': "Add test case details (Name, Description, Steps, etc.)", 
                        'redirect_text': redirect_val, 
                        'severity': 'High'
                    })
                    all_valid = False
                else:
                    # Validate sub-sections (a, b, c, d, e)
                    sub_err = check_itsar_subsections(text_only_content, tid)
                    for err_idx, err in enumerate(sub_err):
                        # Update where to be more specific if possible
                        detailed_where = f"{where_val} - {err['label']}"
                        all_errors_table.append({
                            'sort_key': sort_val + 4 + (err_idx * 0.1),
                            'where': detailed_where, 
                            'what': err['why'], 
                            'suggestion': err['suggestion'], 
                            'redirect_text': redirect_val, 
                            'severity': err.get('severity', 'High')
                        })
                        all_valid = False
                    
                    fig_err = check_figure_ids(content, expected_sub_prefix, tid)
                    for fig_idx, err in enumerate(fig_err):
                        all_errors_table.append({
                            'sort_key': sort_val + 5 + (fig_idx * 0.1),
                            'where': where_val, 
                            'what': err['why'], 
                            'suggestion': err['suggestion'], 
                            'redirect_text': redirect_val, 
                            'severity': err.get('severity', 'Low')
                        })
                        all_valid = False

    except Exception as e:
        print(json.dumps([{"where": "Process Error", "what": str(e), "suggestion": "Fix JSON"}], indent=4))
        sys.exit(1)

    # Sort primarily by sort_key, then by severity
    severity_map = {'High': 0, 'Medium': 1, 'Low': 2}
    all_errors_table.sort(key=lambda x: (x.get('sort_key', 9999), severity_map.get(x.get('severity', 'Low'), 3)))
    
    # Remove sort_key from the final output for cleaner JSON
    final_output = []
    for err in all_errors_table:
        clean_err = {k: v for k, v in err.items() if k != 'sort_key'}
        final_output.append(clean_err)

    print(json.dumps(final_output, indent=4))
    with open('output.json', 'w', encoding='utf-8') as f: json.dump(final_output, f, indent=4)
    sys.exit(1 if not all_valid else 0)

if __name__ == "__main__":
    main()
