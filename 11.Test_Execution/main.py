import sys
import os
from pathlib import Path
import argparse
import re
import json
from typing import List, Dict, Optional, Tuple, Any, Union

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

def normalize_text(text: str) -> str:
    if not text: return ""
    text = text.lower().strip()
    
    # 1. Semantic Normalization: Standardize common terms
    text = re.sub(r'\b(verified|verifying|verification|to\s*verify)\b', 'verify', text)
    text = re.sub(r'\b(supports|supported|supporting)\b', 'support', text)
    text = re.sub(r'\b(mechanism|mechanisms)\b', 'mechanism', text)
    text = re.sub(r'\b(requirement|requirements)\b', 'requirement', text)
    text = re.sub(r'\b(protocol|protocols)\b', 'protocol', text)
    text = re.sub(r'\b(security|secure|secured)\b', 'secure', text)
    
    # 2. General Cleanup
    # Remove common prefixes
    text = re.sub(r'^test\s*case\s*name\s*[:\-]*\s*', '', text)
    text = re.sub(r'^test\s*scen?ario\s*[\d\.\s]+[:\-]*\s*', '', text)
    text = re.sub(r'^positive\s*scenario\s*[:\-]*\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^negative\s*scenario\s*[:\-]*\s*', '', text, flags=re.IGNORECASE)
    
    # Remove all non-alphanumeric except spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Collapse whitespace
    text = " ".join(text.split())
    return text

def check_itsar_subsections(itsar_details: List[str], test_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    definitions = {
        'a': {'label': 'a. Test Case Name', 'keywords': ['test case name', 'testcase name', 'testcasename']},
        'b': {'label': 'b. Test Case Description', 'keywords': ['test case description', 'testcase description', 'testcasedescription', 'description']},
        'c': {'label': 'c. Execution Steps', 'keywords': ['execution steps', 'execution step', 'executionsteps', 'execution']},
        'd': {'label': 'd. Test Observations', 'keywords': ['test observation', 'testobservation', 'observation']},
        'e': {'label': 'e. Evidence Provided', 'keywords': ['evidence provided', 'evidenceprovided', 'evidence']},
    }
    
    # Use a simpler dictionary to track status
    found_map = {k: False for k in definitions}
    content_map = {k: False for k in definitions}
    text_accum = {k: "" for k in definitions}
    wrong_prefix_map = {k: "" for k in definitions}
    format_error_map = {k: False for k in definitions}
    found_header_map = {k: "" for k in definitions}
    intended_header_map = {k: "" for k in definitions}

    current_section = None
    first_line = None
    
    expanded_details = []
    marker_pattern = r'([a-e]\.\s*(?:Test\s*Case\s*Name|Test\s*Case\s*Description|Description|Execution\s*Steps?|Test\s*Observations?|Observations?|Evidence\s*Provided|Evidence))'
    
    for detail in itsar_details:
        if not isinstance(detail, str): continue
        text = detail.strip()
        if not text: continue

        parts = re.split(marker_pattern, text, flags=re.IGNORECASE)
        # re.split with capture groups returns [pre_match, match_group1, post_match_pre_next_match, match_group1, ...]
        # Example: "Intro a.TCName: Content b.TCDesc: More" -> ["Intro ", "a.TCName", ": Content ", "b.TCDesc", ": More"]
        
        # If the first part is not a marker, it's initial content
        if parts and parts[0].strip() and not re.match(marker_pattern, parts[0], re.IGNORECASE):
            expanded_details.append(parts[0].strip())
        
        # Iterate through the rest, combining marker with its content
        for i in range(1, len(parts), 2): # Start from 1, step by 2 to get markers
            marker = parts[i].strip()
            content_after_marker = parts[i+1].strip() if i+1 < len(parts) else ""
            if marker:
                expanded_details.append(f"{marker} {content_after_marker}".strip())
            elif content_after_marker: # Should not happen if marker_pattern is correct, but for safety
                expanded_details.append(content_after_marker)
    
    for text_normalized in [ ' '.join(str(d).split()) for d in expanded_details if d ]:
        text_lower = text_normalized.lower()
        if first_line is None: first_line = text_normalized
        found_marker = False
        
        for key, info in definitions.items():
            prefix = key + "."
            if found_map[key] and not wrong_prefix_map[key]: continue
            
            found_kw = False
            for kw in info['keywords']:
                if kw in text_lower:
                    is_header = False
                    p_head = r'^' + re.escape(prefix) + r'\s*' + re.escape(kw)
                    if re.match(p_head, text_normalized, re.IGNORECASE):
                        is_header = True
                    elif text_lower.startswith(prefix) and kw in text_lower[:50]:
                        is_header = True

                    if is_header:
                        found_map[key] = True
                        current_section = key
                        found_marker = True
                        found_kw = True

                        actual_label_part = text_normalized.split(':')[0].strip()
                        expected_full_label = f"{prefix} {info['label'].split('. ', 1)[1]}"
                        if actual_label_part.lower() != expected_full_label.lower():
                             format_error_map[key] = True
                             found_header_map[key] = text_normalized

                        p_content = r'^' + re.escape(prefix) + r'\s*' + re.escape(kw) + r'[:\-]?\s*'
                        remaining = re.sub(p_content, '', text_normalized, count=1, flags=re.IGNORECASE).strip()
                        if is_meaningful_content(remaining): 
                            content_map[key] = True
                            text_accum[key] = remaining
                        break
                    elif re.match(r'^[\d\w\.]+\s*' + re.escape(kw), text_normalized, re.IGNORECASE):
                        found_map[key] = True
                        wrong_prefix_map[key] = text_normalized
                        current_section = key
                        found_marker = True
                        found_kw = True
                        p_any_prefix = r'^.*?'+re.escape(kw)+r'[:\-]?\s*'
                        remaining = re.sub(p_any_prefix, '', text_normalized, count=1, flags=re.IGNORECASE).strip()
                        if is_meaningful_content(remaining): 
                            content_map[key] = True
                            text_accum[key] = remaining
                        break
            
            if not found_kw and text_lower.startswith(prefix) and not found_map[key]:
                if not intended_header_map[key]:
                    intended_header_map[key] = text_normalized
            
            if found_marker: break
        
        if not found_marker and current_section:
            if is_meaningful_content(text_normalized):
                content_map[current_section] = True
                if text_accum[current_section]:
                    text_accum[current_section] += " " + text_normalized
                else:
                    text_accum[current_section] = text_normalized
                
    errors: List[Dict[str, Any]] = []
    for key, info in definitions.items():
        label = str(info.get('label', ''))
        if not found_map.get(key):
            intended = str(intended_header_map.get(key, ""))
            if intended:
                errors.append({'why': f"Incorrect header format: Found '{intended}'", 'suggestion': f"Expected: '{label}:'", 'label': label, 'severity': 'Medium'})
            else:
                why_msg = f"Missing section: '{label}' section not found"
                if first_line is not None:
                    display_line = first_line[:50] + "..." if len(first_line) > 50 else first_line
                    why_msg += f". Found: '{display_line}'"
                errors.append({'why': why_msg, 'suggestion': f"Add '{label}' section", 'label': label, 'severity': 'High'})
        else:
            if wrong_prefix_map.get(key):
                errors.append({'why': f"Incorrect prefix: Found '{wrong_prefix_map[key]}'", 'suggestion': f"Expected: '{label}:'", 'label': label, 'severity': 'Medium'})
            
            if format_error_map.get(key):
                 header_text = str(found_header_map.get(key, "Unknown"))
                 found_label = header_text.split(':')[0].strip() if ':' in header_text else header_text[:20]
                 errors.append({'why': f"Incorrect header format: Found '{found_label}'", 'suggestion': f"Expected: '{label}:'", 'label': label, 'severity': 'Low'})

            if not content_map.get(key):
                errors.append({'why': f"Missing content: Found empty in '{label}' section", 'suggestion': f"Add content after '{label}'", 'label': label, 'severity': 'High'})
    
    return errors, text_accum

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
        
        # Extract Section 8.1 scenarios
        section_81_scenarios = []
        for s81 in sections:
            s81_title = s81.get('title', '').strip()
            if "8.1. Number of Test Scenarios" in s81_title or re.search(r'^8\.1\.', s81_title):
                scenarios = s81.get('test_scenarios', [])
                for sc in scenarios:
                    desc = sc.get('description', '')
                    if desc:
                        section_81_scenarios.append(desc)
                break
        
        def check_match(expected_txt, target_txt, threshold=0.98):
            if not expected_txt or not target_txt: return False
            norm_exp = normalize_text(expected_txt)
            norm_target = normalize_text(target_txt)
            # (Substring shortcut removed for strict 98% keyword matching)
            
            # Semantic Keyword match
            keywords = [w for w in norm_exp.split() if len(w) > 3 and w not in ['the', 'and', 'with', 'that', 'this', 'for', 'are']]
            if keywords:
                k_matches = sum(1 for kw in keywords if kw in norm_target)
                if k_matches / len(keywords) >= threshold: return True
            return False
        
        # 3.5. Extract Section 8.4 Test Scenario Headings (Fallback Cycle Check)
        section_84_test_names = []
        target_84 = None
        for sec in sections:
            st = sec.get('title', '').strip().lower()
            if '8.4.' in st or ('8.4' in st and 'execution' in st and 'step' in st):
                target_84 = sec
                break
        
        if target_84:
            steps_data = target_84.get('execution_steps', [])
            if steps_data:
                for item in steps_data:
                    if isinstance(item, dict):
                        h = item.get('test_scenario', '')
                        steps = item.get('steps', [])
                        # Extract only step with order 0
                        step_0 = " ".join([str(s.get('step', '')) if isinstance(s, dict) else str(s) for s in steps if s.get('order') == 0])
                        if step_0:
                            section_84_test_names.append(step_0.strip())
                        else:
                            section_84_test_names.append(str(h).strip())
            else:
                for it in target_84.get('content', []):
                    txt = it.get('text', '') if isinstance(it, dict) else str(it)
                    if "test scenario" in txt.lower():
                        section_84_test_names.append(txt.strip())
        
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
        expected_title_11 = "11. Test Execution"
        title_lower = found_title.lower()
        num_match = re.match(r'^([\d\.]+)', found_title)
        has_any_number = num_match is not None
        has_correct_num = found_title.startswith("11.")
        display_title_11 = expected_title_11

        # Determine redirect_title (without prefix) for UI redirection
        redirect_title_11 = re.sub(r'^[\d\.]+\s*', '', found_title).strip() or found_title
        
        if not (has_correct_num and "test execution" in title_lower):
            error_details = []
            if has_any_number and not has_correct_num:
                wrong_num = num_match.group(1).strip()
                error_details.append(f"Wrong section number (Found: '{wrong_num}', Expected: '11.')")
            elif not has_any_number:
                error_details.append(f"Section number is missing (Found: '{found_title}')")

            if "test execution" not in title_lower:
                is_space_issue = any(part in title_lower for part in ["testexecution", "11..", "test-execution"])
                if is_space_issue:
                    error_details.append(f"Incorrect formatting - space issue (Found: '{found_title}')")
                else:
                    error_details.append(f"Incorrect formatting (Found: '{found_title}')")
            
            if error_details:
                all_errors_table.append({
                    "sort_key": 5,
                    "where": display_title_11,
                    "what": "Section title is incorrect. " + " ".join(error_details),
                    "suggestion": f"Fix the title to exactly match: '{expected_title_11}'",
                    "redirect_text": redirect_title_11,
                    "severity": "Low"
                })
            # proceed to content check if we have the body
            
        in_section_11 = False
        section11_found = True # Since we found it above
        current_test_case_number = None
        found_test_case_numbers = []
        found_test_ids = []
        sub_prefix_base = "11.1" # Default base

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
                          found_test_ids.append({'id': m.group(1), 'title': t, 'section': section, 'test_case_number': num, 'tc_section_title': title_text, 'is_embedded': True, 'content_list': content_list, 'missing_space': False})
                      elif m_relax:
                          extracted_id = m_relax.group(1)
                          # Dynamically derive expected suffix from text after the ID (not hardcoded)
                          raw_after = t[len(extracted_id):].strip().lstrip(':- ')
                          exp_suffix = raw_after if raw_after else 'ITSAR WiFi-CPE'
                          
                          expected_sub_prefix_p1 = f"{sub_prefix_base}.{len(found_test_case_numbers)}"
                          current_idx = len(found_test_case_numbers)
                          all_errors_table.append({
                              'sort_key': current_idx * 1000 + 49,
                              'where': f'11. Test Execution - Test Case Number {expected_sub_prefix_p1} - Test Case {extracted_id}',
                              'what': f"Incorrect format: Missing space after ID in '{t}'",
                              'suggestion': f"Expected: '{extracted_id} {exp_suffix}'",
                              'redirect_text': title_text,
                              'severity': 'Low'
                          })
                          all_valid = False
                          found_test_ids.append({'id': extracted_id, 'title': t, 'section': section, 'test_case_number': num, 'tc_section_title': title_text, 'is_embedded': True, 'content_list': content_list, 'missing_space': True})
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
                    found_test_ids.append({'id': tid, 'title': title_text, 'section': section, 'test_case_number': current_test_case_number, 'tc_section_title': title_text, 'is_embedded': False, 'content_list': None})
                    section11_found = True

        if not section11_found:
             all_errors_table.append({'sort_key': 0, 'where': "Test Execution", 'what': "Section 11 Missing", 'suggestion': "Add Section 11", 'redirect_text': "Section 11 Missing", 'severity': 'High'})
        else:
            if all_errors_table: all_valid = False
            
            base_suffix = base_id.split('.')[-1] if base_id and '.' in base_id else "1"
            if found_test_case_numbers:
                first_tc = found_test_case_numbers[0]['number']
                parts = first_tc.split('.')
                if len(parts) >= 2 and parts[0] == "11":
                    # If it's a valid 11.x format, use that base
                    sub_prefix_base = ".".join(parts[:-1])

            for i, tc in enumerate(found_test_case_numbers, 1):
                num = tc['number']
                l3_exp = f"{sub_prefix_base}.{i}"
                where_sub = f"11. Test Execution - Subsection {l3_exp}"
                sort_val = i * 1000  # Base sort key for this TC index
                
                # Check format "ID Test Case Number:"
                l3_exp_clean = l3_exp.strip('.')
                expected_sub_title = f"{l3_exp_clean} Test Case Number:"
                alt_expected = f"{l3_exp_clean}. Test Case Number:"
                actual_title = tc['title'].strip()
                actual_title_lower = actual_title.lower()
                
                # Consolidated Format Check
                actual_clean = " ".join(actual_title.split()).strip()
                
                if actual_clean not in [expected_sub_title, alt_expected]:
                    err_msgs = []
                    # 1. Sequence/ID error
                    if num != l3_exp:
                        err_msgs.append(f"Incorrect sequence/base: Found '{num}' instead of '{l3_exp}'")
                    
                    # 2. Specific Space Check (e.g., '11.1.3Test' or '11.1.1TestCase')
                    found_id_pattern = re.escape(num.strip('.'))
                    is_crushed_id = re.match(r'^' + found_id_pattern + r'[^ \.\-\–\s]', actual_title)
                    
                    is_space_issue = (
                        is_crushed_id or 
                        "testcase" in actual_title_lower or 
                        "casenumber" in actual_title_lower or
                        "word-based" in actual_title_lower or
                        ".." in actual_title
                    )
                    
                    if is_space_issue:
                        err_msgs.append(f"Incorrect formatting - space issue (Found: '{actual_title}')")
                    elif actual_clean != expected_sub_title and num == l3_exp:
                         err_msgs.append(f"Incorrect title format: Found '{actual_clean}'")

                    if err_msgs:
                        all_errors_table.append({
                            'sort_key': sort_val,
                            'where': where_sub, 
                            'what': "Section title is incorrect. " + " ".join(err_msgs), 
                            'suggestion': f"Expected: '{expected_sub_title}'", 
                            'redirect_text': re.sub(r'^[\d\.]+\s*', '', str(tc['title'])).strip(),
                            'severity': 'Low'
                        })
                    all_valid = False
                elif actual_title not in [expected_sub_title, alt_expected]:
                    # Cleaned matches but original has spacing issues
                    all_errors_table.append({
                        'sort_key': sort_val + 3,
                        'where': where_sub, 
                        'what': f"Incorrect formatting (space issue) in the title. Found: '{actual_title}'", 
                        'suggestion': f"Expected: '{expected_sub_title}'", 
                        'redirect_text': f"{tc['title']}", 
                        'severity': 'Low'
                    })
                    all_valid = False
            
            # Create a lookup for expected subsection IDs using the actual found index to ensure figures are validated against the CORRECT sequence
            tc_expected_map = {}
            for idx, tc in enumerate(found_test_case_numbers, 1):
                # We map the found number to what it SHOULD be
                tc_expected_map[tc['number']] = f"{sub_prefix_base}.{idx}"
            
            tc_title_map = {tc['number']: tc['title'] for tc in found_test_case_numbers}
            
            for i, test in enumerate(found_test_ids, 1):
                tid = test['id']
                tc_num = test.get('test_case_number')
                
                # FORCE expected_sub_prefix to be based STRICTLY on its position in the document
                # This ensures if the title says 11.1.3 but is at position 1 (i=1), we use 11.1.1 for figures
                expected_sub_prefix = f"{sub_prefix_base}.{i}"
                
                # Derive expected ID based on its actual position in the document
                exp_id = f"{base_id}.{i}" if base_id else tid
                
                # Use expected_sub_prefix for the 'where' field to show the CORRECT intended location
                where_val = f"11. Test Execution - Test Case Number {expected_sub_prefix} - Test Case {exp_id}"
                redirect_val = test.get('tc_section_title', tid)
                sort_val = i * 1000 + 50 

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
                
                # Check for space after ID: skip if already flagged by relaxed match
                if not test.get('missing_space', False) and tid in actual_test_title and not re.match(r'^' + re.escape(tid) + r'[:\-–\.\s]', actual_test_title):
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
                    orig_sub_err, sections_text = check_itsar_subsections(text_only_content, tid)
                                  # 4. Content Validation against 8.1 (Scenario Description) OR 8.4 (Scenario Heading)
                    tc_name_error = None
                    exp_scenario_desc = None
                    found_in_triad = False
                    idx = i - 1
                    exp_scenario_desc = ""

                    def check_tc_name_match(expected_txt, local_normalized, full_combined_text):
                        if not expected_txt: return False
                        # 1. Direct substring check in Section (a/b) content
                        if check_match(expected_txt, local_normalized): return True
                        # 2. Fallback check on entire test case combined content
                        if check_match(expected_txt, full_combined_text): return True
                        return False

                    full_combined_normalized = normalize_text(" ".join(text_only_content))
                    
                    source_ref = ""
                    # Try matching against 8.1
                    if idx < len(section_81_scenarios):
                        exp_scenario_desc = section_81_scenarios[idx]
                        source_ref = "Section 8.1 (Scenario Description)"
                        if check_tc_name_match(exp_scenario_desc, "", full_combined_normalized):
                            found_in_triad = True
                    
                    # Fallback cycle check against 8.4
                    if not found_in_triad and idx < len(section_84_test_names):
                        fallback_84_desc = section_84_test_names[idx]
                        if check_tc_name_match(fallback_84_desc, "", full_combined_normalized):
                            found_in_triad = True
                            exp_scenario_desc = fallback_84_desc
                            source_ref = "Section 8.4 (Step 1)"

                    # Error Tracking for a and b
                    tc_name_error = None
                    tc_desc_error = None
                    
                    if exp_scenario_desc:
                        # Check Name (a.)
                        name_text = sections_text.get('a', '').strip()
                        if not name_text: 
                            tc_name_error = "missing"
                        elif not check_match(exp_scenario_desc, normalize_text(name_text)):
                            tc_name_error = "wrong"
                        
                        # Check Description (b.)
                        desc_text = sections_text.get('b', '').strip()
                        if not desc_text:
                            tc_desc_error = "missing"
                        elif not check_match(exp_scenario_desc, normalize_text(desc_text)):
                             # If match is found in full combined content but not specifically in b., report as 'wrong' only if name is also wrong
                             if tc_name_error: tc_desc_error = "wrong"
                             # Alternatively: if Name is correct but Description is totally different, flag it.
                    
                    # Process original subsection errors, consolidating with our new checks
                    managed_labels = ['a. Test Case Name', 'b. Test Case Description']
                    for err_idx, err in enumerate(orig_sub_err):
                        label = err.get('label', '')
                        # Handle managed labels separately
                        if label in managed_labels:
                            # Skip generic "missing" or "not found" if we are about to report specifically
                            if "Missing content" in err['why'] or "section not found" in err['why']:
                                continue
                            
                        detailed_where = f"{where_val} - {label}"
                        all_errors_table.append({
                            'sort_key': sort_val + 4 + (err_idx * 0.1),
                            'where': detailed_where, 
                            'what': err['why'], 
                            'suggestion': err['suggestion'], 
                            'redirect_text': redirect_val, 
                            'severity': err.get('severity', 'High')
                        })
                    
                    # Error processing with instruction-based suggestions
                    suggestion_text = f"Synchronize with {source_ref} content." if source_ref else "Provide valid technical details."

                    if tc_name_error:
                        all_errors_table.append({
                            'sort_key': sort_val + 4,
                            'where': f"{where_val} - a. Test Case Name",
                            'what': f"test case name content {tc_name_error}.",
                            'suggestion': suggestion_text,
                            'redirect_text': redirect_val,
                            'severity': 'High'
                        })
                    
                    if tc_desc_error:
                        all_errors_table.append({
                            'sort_key': sort_val + 4.1,
                            'where': f"{where_val} - b. Test Case Description",
                            'what': f"test case description content {tc_desc_error}.",
                            'suggestion': suggestion_text,
                            'redirect_text': redirect_val,
                            'severity': 'High'
                        })
                    
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

            # Check for missing scenarios from 8.1 in Section 11
            found_scenarios_indices = set()
            for test in found_test_ids:
                # Try to map test ID to its index in 8.1
                tid = test['id']
                for idx, s81_desc in enumerate(section_81_scenarios, 1):
                    # We assume sequential order for mapping if IDs don't match exactly
                    pass
                # Actually, we use the loop index 'i' above. 
                # Let's just check if we have fewer test IDs than scenarios.
            
            if len(found_test_ids) < len(section_81_scenarios):
                for i in range(len(found_test_ids) + 1, len(section_81_scenarios) + 1):
                    exp_id = f"{base_id}.{i}" if base_id else f"Scenario {i}"
                    all_errors_table.append({
                        "sort_key": i * 1000 + 999,
                        "where": f"11. Test Execution - Test Case {exp_id}",
                        "what": "test case name content missing. (Missing scenario from 8.1)",
                        "suggestion": f"Expected: '{section_81_scenarios[i-1]}'",
                        "redirect_text": "Test Execution",
                        "severity": "High"
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
