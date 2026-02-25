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
    temp = re.sub(r'Test\s+Sc[eh]n?ario\s*[:.-]*', '', cleaned, flags=re.IGNORECASE).strip()
    temp = re.sub(r'Test\s+Case\s+Number\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()
    temp = re.sub(r'[a-e]\.\s*(Test\s+Case\s+Name|Test\s+Case\s+Description|Description|Execution\s+Steps|Test\s+Observations|Evidence\s+Provided)\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()
    temp = re.sub(r'TC\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()

    if not temp or temp.lower() in [".", ":", "-", "_", "...", "n/a", "none", "nil"]:
        return False
    if not re.search(r'\w', temp):
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
                        sections_status[key]['intended_header'] = None # Found correctly
                        current_section = key
                        found_marker = True
                        found_kw = True
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
                sev = 'medium'
            else:
                why = f"Missing section: '{label}' section not found"
                if first_line:
                    display_line = first_line[:50] + "..." if len(first_line) > 50 else first_line
                    why += f". Found: '{display_line}'"
                suggestion = f"Add '{label}' section"
                sev = 'high'
            
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
                    'severity': 'medium'
                })
            if not status['has_content']:
                why = f"Missing content: Found empty in '{label}' section"
                errors.append({
                    'why': why, 
                    'suggestion': f"Add content after '{label}'", 
                    'label': label,
                    'severity': 'high'
                })
    return errors

def check_figure_ids(itsar_details: List[str], expected_tc_number: str, test_id: str) -> List[Dict]:
    errors = []
    # Match both captions like "Figure 11.1.1.1 - Title" and mentions like "(refer figure 11.1.1.1)"
    figure_caption_pattern = re.compile(r'^[Ff]igure\s+([\d\.]+)\s*[-–:](.*)$', re.IGNORECASE)
    figure_any_pattern = re.compile(r'[Ff]igure\s+([\d\.]+)', re.IGNORECASE)
    
    found_captions = []
    all_mentions = []
    
    for detail in itsar_details:
        if not isinstance(detail, str): continue
        text = detail.strip()
        
        # 1. Identify captions for sequence and title checking
        cap_match = figure_caption_pattern.match(text)
        if cap_match:
            full_id = cap_match.group(1).strip('.')
            figure_title = cap_match.group(2).strip()
            parts = full_id.split('.')
            fig_data = {
                'full_id': full_id, 
                'title': figure_title,
                'suffix': int(parts[-1]) if parts[-1].isdigit() else 0
            }
            found_captions.append(fig_data)
        
        # 2. Identify all mentions for alignment checking
        mentions = figure_any_pattern.findall(text)
        for m in mentions:
            all_mentions.append(m.strip('.'))
    
    # Check captions sequentially
    expected_suffix = 1
    for i, fig in enumerate(found_captions, 1):
        actual_id = fig['full_id']
        correct_id = f"{expected_tc_number}.{expected_suffix}"
        
        if not actual_id.startswith(expected_tc_number):
            errors.append({
                'type': 'figure_id', 
                'why': f"Incorrect Figure ID alignment: Found 'Figure {actual_id}'", 
                'suggestion': f"Expected to start with '{expected_tc_number}' (e.g. Figure {correct_id})", 
                'severity': 'low'
            })
        elif fig['suffix'] != expected_suffix:
            errors.append({
                'type': 'figure_id', 
                'why': f"Incorrect Figure ID sequence: Found 'Figure {actual_id}'", 
                'suggestion': f"Expected Figure {correct_id}", 
                'severity': 'low'
            })
            
        if not is_meaningful_content(fig['title']):
            errors.append({
                'type': 'figure_title', 
                'why': f"Figure title missing: Found '{fig['title']}' for Figure {actual_id}", 
                'suggestion': f"Add a descriptive title for Figure {actual_id}", 
                'severity': 'medium'
            })
        expected_suffix += 1

    # Check all other mentions for general alignment
    for m in all_mentions:
        if not m.startswith(expected_tc_number):
            if not any(f['full_id'] == m for f in found_captions if not f['full_id'].startswith(expected_tc_number)):
                errors.append({
                    'type': 'figure_id', 
                    'why': f"Incorrect figure alignment in text: Found 'figure {m}'", 
                    'suggestion': f"Ensure Figure IDs in this section start with '{expected_tc_number}'", 
                    'severity': 'low'
                })

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
                sec_id = section.get('section_id', '')
                
                is_req_sec = sec_id == 'SEC-02' or re.search(r'Security\s+Requirement', title, re.IGNORECASE) or re.search(r'^2\.', title)
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

        in_section_11 = False
        section11_found = False
        section11_found_via_header = False
        section11_title_error = None
        found_test_ids = []
        found_test_case_numbers = []
        current_test_case_number = None


        for section in sections:
            title = section.get('title', '').strip()
            level = section.get('level', 0)
            sec_id = section.get('section_id', 'Unknown')
            
            title_lower = title.lower()
            is_sec_11_candidate = "11" in title_lower and "test" in title_lower and "execution" in title_lower
            
            if (is_sec_11_candidate and level == 1) or (is_sec_11_candidate and not in_section_11):
                in_section_11 = True
                section11_found = True
                section11_found_via_header = True
                if not re.match(r'^11\.\s+Test\s+Execution:?$', title, re.IGNORECASE):
                     section11_title_error = {
                        'where': "Test Execution - 11. Test Execution:",
                        'what': f"Incorrect Title: '{title}'",
                        'suggestion': "Expected: '11. Test Execution:'",
                        'redirect_text': title,
                        'severity': 'medium'
                     }
                continue
            
            if in_section_11 and re.match(r'^(12|10|13)(\.|\s)', title):
                 in_section_11 = False
                 continue

            if re.match(r'^11\.', title) and not in_section_11:
                in_section_11 = True

            if not in_section_11: continue

            if re.match(r'^11\.', title):
                 match_num = re.match(r'^(11[\d\s\.]+)', title)
                 num = match_num.group(1).replace(' ', '').strip(':').strip('.') if match_num else title.split(' ', 1)[0].replace(' ', '').strip(':').strip('.')
                 is_correct = "Test Case Number:" in title
                 found_test_case_numbers.append({'number': num, 'title': title, 'is_correct_format': is_correct, 'section_id': sec_id})
                 current_test_case_number = num
                 section11_found = True
                 content_list = []
                 if 'content' in section:
                     for item in section['content']:
                         t = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                         if not t: continue
                         content_list.append(t)
                         
                         m = test_id_pattern.match(t)
                         if m:
                             found_test_ids.append({'id': m.group(1), 'title': t, 'section_id': sec_id, 'section': section, 'test_case_number': num, 'is_embedded': True, 'content_list': content_list})
                 continue

            if re.search(r'^\d+\.\d+\.\d+\.\d+', title):
                 match = test_id_pattern.match(title)
                 if match or "itsar" in title.lower():
                    tid = match.group(1) if match else title.split(' ')[0]
                    if tid.startswith('12.') or tid.startswith('10.'): continue 
                    found_test_ids.append({'id': tid, 'title': title, 'section_id': sec_id, 'section': section, 'test_case_number': current_test_case_number, 'is_embedded': False, 'content_list': None})
                    section11_found = True

        if not section11_found:
             all_errors_table.append({'where': "Test Execution", 'what': "Section 11 Missing", 'suggestion': "Add Section 11", 'redirect_text': "Section 11 Missing", 'severity': 'high'})
             all_valid = False
        else:
            if section11_title_error:
                all_errors_table.append(section11_title_error)
                all_valid = False
            
            if not section11_found_via_header:
                all_errors_table.append({'where': "Test Execution - 11. Test Execution:", 'what': "Missing or Incorrect Section 11 Main Header", 'suggestion': "Expected: '11. Test Execution:'", 'redirect_text': "Section 11", 'severity': 'medium'})
                all_valid = False
            
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
                
                # Check format "ID Test Case Number:"
                expected_title = f"{l3_exp} Test Case Number:"
                actual_clean = " ".join(tc['title'].split()).strip()
                
                if actual_clean != expected_title:
                    if num != l3_exp:
                        # Priority 1: Sequence/ID error
                        what_msg = f"Incorrect sequence/base: Found '{num}' instead of '{l3_exp}'"
                        sev = 'low'
                    else:
                        # Priority 2: Format error
                        what_msg = f"Incorrect title format: Found '{actual_clean}'"
                        sev = 'medium'
                        
                    all_errors_table.append({
                        'where': where_sub, 
                        'what': what_msg, 
                        'suggestion': f"Expected: '{expected_title}'", 
                        'redirect_text': f"{tc['title']}", 
                        'severity': sev
                    })
                    all_valid = False
            
            # Create a lookup for expected subsection IDs
            tc_expected_map = {tc['number']: f"{sub_prefix_base}.{idx}" for idx, tc in enumerate(found_test_case_numbers, 1)}
            tc_title_map = {tc['number']: tc['title'] for tc in found_test_case_numbers}
            for i, test in enumerate(found_test_ids, 1):
                tid = test['id']
                tc_num = test.get('test_case_number')
                exp_id = f"{base_id}.{i}" if base_id else tid
                
                # Find the CORRECT expected subsection suffix
                expected_sub_prefix = tc_expected_map.get(tc_num, tc_num)
                
                # New descriptive 'where' field using the EXPECTED number for location clarity
                where_val = f"11. Test Execution - Test Case Number {expected_sub_prefix} - Test Case {exp_id}"
                redirect_val = tc_title_map.get(tc_num, tid)

                # 1. Base ID Check
                is_base_mismatch = False
                if base_id and tid:
                    found_parts = tid.split('.')
                    if len(found_parts) >= 3:
                        if ".".join(found_parts[:3]) != base_id:
                            is_base_mismatch = True
                
                if is_base_mismatch:
                    all_errors_table.append({
                        'where': where_val, 
                        'what': f"Base ID mismatch: Found '{tid}'. expected prefix '{base_id}'.", 
                        'suggestion': f"Ensure Base ID is {base_id}", 
                        'redirect_text': redirect_val, 
                        'severity': 'low'
                    })
                    all_valid = False

                # 2. Sequence Check
                if tid != exp_id:
                    all_errors_table.append({
                        'where': where_val, 
                        'what': f"Incorrect sequence: Found '{tid}' instead of '{exp_id}'", 
                        'suggestion': f"Fix ID to {exp_id}", 
                        'redirect_text': redirect_val, 
                        'severity': 'low'
                    })
                    all_valid = False
                
                # 3. Label Check "ITSAR WiFi-CPE"
                expected_title_suffix = "ITSAR WiFi-CPE"
                if tid in test['title']:
                    rem = test['title'].split(tid, 1)[1].strip()
                    if expected_title_suffix.lower() not in rem.lower():
                        all_errors_table.append({
                            'where': where_val, 
                            'what': f"Incorrect Title suffix: Found '{rem}' instead of '{expected_title_suffix}'", 
                            'suggestion': f"Expected format: '{exp_id} {expected_title_suffix}'", 
                            'redirect_text': redirect_val, 
                            'severity': 'medium'
                        })
                        all_valid = False

                # 4. Content Validation
                content = []
                if test['is_embedded']: 
                    content = test['content_list']
                elif 'itsar_section_details' in test['section']: 
                    content = test['section']['itsar_section_details']
                elif 'content' in test['section']:
                    for it in test['section']['content']: 
                        content.append(it.get('text', '') if isinstance(it, dict) else str(it))
                
                if not content or not any(is_meaningful_content(c) for c in content):
                    all_errors_table.append({
                        'where': where_val, 
                        'what': "Content missing: Test case details are missing or empty", 
                        'suggestion': "Add test case details (Name, Description, Steps, etc.)", 
                        'redirect_text': redirect_val, 
                        'severity': 'high'
                    })
                    all_valid = False
                else:
                    # Validate sub-sections (a, b, c, d, e)
                    sub_err = check_itsar_subsections(content, tid)
                    for err in sub_err:
                        # Update where to be more specific if possible
                        detailed_where = f"{where_val} - {err['label']}"
                        all_errors_table.append({
                            'where': detailed_where, 
                            'what': err['why'], 
                            'suggestion': err['suggestion'], 
                            'redirect_text': redirect_val, 
                            'severity': err.get('severity', 'high')
                        })
                        all_valid = False
                    
                    fig_err = check_figure_ids(content, expected_sub_prefix, tid)
                    for err in fig_err:
                        all_errors_table.append({
                            'where': where_val, 
                            'what': err['why'], 
                            'suggestion': err['suggestion'], 
                            'redirect_text': redirect_val, 
                            'severity': 'low'
                        })
                        all_valid = False

    except Exception as e:
        print(json.dumps([{"where": "Process Error", "what": str(e), "suggestion": "Fix JSON"}], indent=4))
        sys.exit(1)

    all_errors_table.sort(key=lambda x: {'high': 0, 'medium': 1, 'low': 2}.get(x.get('severity', 'low'), 3))
    print(json.dumps(all_errors_table, indent=4))
    with open('output.json', 'w', encoding='utf-8') as f: json.dump(all_errors_table, f, indent=4)
    sys.exit(1 if not all_valid else 0)

if __name__ == "__main__":
    main()
