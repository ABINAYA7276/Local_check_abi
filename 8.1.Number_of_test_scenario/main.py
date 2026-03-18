import sys
import io
from pathlib import Path
import os
import argparse
import re
import json
from typing import List, Dict, Tuple, Optional

def is_meaningful_content(text: str) -> bool:
    if not text: return False
    text = text.strip().lower()
    if text == 'na': return True
    if text in ['none', 'n/a', 'nil', '.', '-', '_', '...'] or len(text) < 3: return False
    if all(c in '.-_,;:!? ' for c in text): return False
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

def main():
    parser = argparse.ArgumentParser(description="Validate Section 8.1: Number of Test Scenarios.")
    parser.add_argument("json_file", type=str, help="Path to the structured JSON file")
    args = parser.parse_args()
    
    json_file = Path(args.json_file)
    if not json_file.is_file():
        print(json.dumps([{"where": "System", "what": f"File not found: {json_file}", "severity": "High"}]))
        sys.exit(1)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    json_path = str(json_file)
    all_errors_table = []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        test_id_pattern = re.compile(r'(\d+(?:\s*[\. ]\s*\d+){3,})')

        # 1. Get base IDs
        base_id = None
        fp_content = data.get('frontpage_data', {}).get('content', [])
        for item in fp_content:
            m = re.search(r'(\d+(?:\s*[\. ]\s*\d+){2})', str(item))
            if m:
                base_id = re.sub(r'[\s]+', '', m.group(1))
                break
        
        if not base_id:
            for section in sections:
                title = section.get('title', '').strip()
                if "Requirement No & Name" in title or re.search(r'^[2]\.', title):
                    fields = ['security_requirement', 'itsar_section_details', 'content']
                    for field in fields:
                        val = section.get(field, '')
                        if not val: continue
                        vals = val if isinstance(val, list) else [val]
                        for v in vals:
                            text = v.get('text', '') if isinstance(v, dict) else str(v)
                            m = re.search(r'(\d+(?:\s*[\. ]\s*\d+){2})', text.strip())
                            if m: 
                                base_id = re.sub(r'[\s]+', '', m.group(1))
                                break
                        if base_id: break
                if base_id: break

        # 2. Extract Section 8.4 and Section 11 content for Cycle Check
        section_84_test_names = []
        section_11_test_names = []

        for sec in sections:
            st = sec.get('title', '').strip().lower()
            # Extract 8.4
            if '8.4.' in st or ('8.4' in st and 'execution' in st and 'step' in st):
                steps_data = sec.get('execution_steps', [])
                if steps_data:
                    for item in steps_data:
                        if isinstance(item, dict):
                            h = item.get('test_scenario', '')
                            steps = item.get('steps', [])
                            step_0 = " ".join([str(s.get('step', '')) if isinstance(s, dict) else str(s) for s in steps if s.get('order') == 0])
                            if step_0:
                                section_84_test_names.append(step_0.strip())
                            else:
                                section_84_test_names.append(str(h).strip())
                else:
                    for it in sec.get('content', []):
                        txt = it.get('text', '') if isinstance(it, dict) else str(it)
                        if "test scenario" in txt.lower():
                            section_84_test_names.append(txt.strip())
            
            # Extract 11
            if re.match(r'^11\.', st) and ('test case number' in st or 'testcase number' in st):
                content_items = sec.get('itsar_section_details', sec.get('content', []))
                items = content_items if isinstance(content_items, list) else [content_items]
                current_name = ""
                found_a = False
                for it in items:
                    txt = it.get('text', '') if isinstance(it, dict) else str(it)
                    if not txt.strip(): continue
                    if re.match(r'^[a]\.\s*', txt.strip(), re.IGNORECASE):
                        current_name = re.sub(r'^[a]\.\s*(Test\s*Case\s*Name|TestCaseName|Test\s*Case\s*Description|Description)\s*[:.-]*', '', txt.strip(), flags=re.IGNORECASE).strip()
                        found_a = True
                        if current_name: break
                    elif found_a and not current_name and len(txt.strip()) > 5:
                        current_name = txt.strip()
                        break
                section_11_test_names.append(current_name)

        standard_title = "8.1. Number of Test Scenarios"
        redirect_stable = "Number of Test Scenarios"
        
        # 3. Check for Section 8.1 Identification
        target_section = None
        for section in sections:
            title = section.get('title', '').strip().replace('\n', ' ')
            title_lower = title.lower()
            if 'number' in title_lower and 'test' in title_lower and 'scenario' in title_lower and '8.1' in title_lower:
                target_section = section
                break

        if not target_section:
            print(json.dumps([{
                "where": standard_title,
                "what": "Section 8.1 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            }], indent=4))
            sys.exit(0)

        section = target_section
        found_title = section.get('title', '').strip().replace('\n', ' ')
        title_lower = found_title.lower()

        # 4. TITLE VALIDATION
        has_body = 'number' in title_lower and 'test' in title_lower and 'scenario' in title_lower
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("8.1.")

        if not (has_correct_num and has_body):
            error_details = []
            if has_body and has_any_number and not has_correct_num:
                wrong_num = num_prefix_match.group(1).strip()
                error_details.append(f"Wrong section number (Found: '{wrong_num}', Expected: '8.1.')")
            elif has_body and not has_any_number:
                error_details.append(f"Section number is missing (Found: '{found_title}')")

            if error_details:
                all_errors_table.append({
                    "where": standard_title,
                    "what": "Section title is incorrect. " + " ".join(error_details),
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })

        # 5. CONTENT VALIDATION
        actual_redirect = re.sub(r'^[\d\.]+\s*', '', found_title).replace(':', '').strip() or redirect_stable
        section81_has_content = False
        position = 0
        
        scenarios_in_json = section.get('test_scenarios', [])
        content_items = section.get('content', [])
        
        parsed_scenarios = []
        if scenarios_in_json:
            for item in scenarios_in_json:
                if isinstance(item, dict):
                    id_val = item.get('test_scenario', '')
                    desc_val = item.get('description', '')
                    h = " ".join([str(i) for i in id_val if i]).strip() if isinstance(id_val, list) else str(id_val).strip()
                    d = " ".join([str(i) for i in desc_val if i]).strip() if isinstance(desc_val, list) else str(desc_val).strip()
                    parsed_scenarios.append({'header': h, 'desc': d})
                else:
                    parsed_scenarios.append({'header': str(item).strip(), 'desc': ''})
        else:
            raw_text_blocks = []
            for item in content_items:
                txt = item.get('text', '') if isinstance(item, dict) else str(item)
                if txt.strip(): raw_text_blocks.append(txt.strip())
            full_text = " ".join(raw_text_blocks)
            parts = re.split(r'(?=\b\d+(?:\s*[. ]\s*\d+){3,}\b)', full_text)
            for p in parts:
                p = p.strip()
                if not p: continue
                m = test_id_pattern.search(p)
                if m:
                    idx_m = m.start()
                    parsed_scenarios.append({'header': p[:idx_m+len(m.group(0))].strip(), 'desc': p[idx_m+len(m.group(0)):].strip()})
                else:
                    if parsed_scenarios: parsed_scenarios[-1]['desc'] += " " + p
                    else: parsed_scenarios.append({'header': '', 'desc': p})

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

        for item in parsed_scenarios:
            position += 1
            section81_has_content = True
            header = item['header']
            desc = item['desc']
            combined = (header + " " + desc).strip()
            id_match = test_id_pattern.search(combined)
            
            exp_id = f"{base_id}.{position}" if base_id else f"X.X.X.{position}"
            where_ref = f"{standard_title} - Test Scenario {position}"
            
            title_errors = []

            # 1. Prefix & Space Check
            clean_header = re.sub(r'[:.\s]+$', '', header).strip()
            # Extract text before ID
            prefix_text = ""
            if id_match:
                prefix_text = header[:id_match.start()].strip()
            
            # Check for correct "Test Scenario" wording
            if prefix_text:
                # Catch "TestScenario" (missing space)
                if re.fullmatch(r'TestScenario', prefix_text, re.IGNORECASE):
                    title_errors.append("Incorrect format: Found 'TestScenario' (missing space)")
                # Catch garbage or typos (like "Scentest scenarioario")
                elif not re.fullmatch(r'Test\s+Scenario', prefix_text, re.IGNORECASE):
                    title_errors.append(f"Garbage text in title: Found '{prefix_text}', Expected: 'Test Scenario'")
            else:
                # ID without "Test Scenario" prefix
                if id_match: title_errors.append("Missing prefix 'Test Scenario' before the ID")

            # 2. ID Check
            if not id_match:
                title_errors.append(f"test scenario ID missing. Found: '{header[:30]}'")
            else:
                found_id_raw = id_match.group(1)
                found_id = re.sub(r'[\s]+', '', found_id_raw)
                found_parts = found_id.split('.')
                found_base = ".".join(found_parts[:-1]) if len(found_parts) > 1 else ""
                found_seq = found_parts[-1] if found_parts else ""
                if (base_id and found_base != base_id) or found_seq != str(position):
                    title_errors.append(f"test scenario id wrong. Found '{found_id}', Expected: {exp_id}")

            if title_errors:
                all_errors_table.append({
                    "where": where_ref,
                    "what": " | ".join(title_errors) + " (Alignment mismatch)" if id_match else " | ".join(title_errors),
                    "suggestion": f"Expected: {exp_id}",
                    "redirect_text": actual_redirect,
                    "severity": "High" if not id_match else "Low"
                })
                if not id_match: continue

            # Content CYCLE Check
            idx = position - 1
            is_valid = False
            where_content = f"{where_ref} - Content"
            
            # Individual check: prioritize the description part for the semantic check
            check_text = desc
            
            if is_meaningful_content(check_text):
                # Check against 8.4
                if idx < len(section_84_test_names):
                    if check_match(check_text, section_84_test_names[idx]): is_valid = True
                
                # Check against 11
                if not is_valid and idx < len(section_11_test_names):
                    if check_match(check_text, section_11_test_names[idx]): is_valid = True
                
                if not is_valid:
                    source_ref = ""
                    if idx < len(section_84_test_names): source_ref = "Section 8.4 (Step 1)"
                    elif idx < len(section_11_test_names): source_ref = "Section 11 (Test Case Name)"
                    
                    if source_ref:
                        suggestion_text = f"Synchronize with {source_ref} content."
                    else:
                        suggestion_text = "Provide valid technical description."

                    found_text_snippet = check_text[:100].strip() + ("..." if len(check_text) > 100 else "")
                    
                    all_errors_table.append({
                        "where": where_content, 
                        "what": f"test scenario content wrong. Found: '{found_text_snippet}'",
                        "suggestion": suggestion_text,
                        "redirect_text": actual_redirect, 
                        "severity": "High"
                    })
            else:
                # Missing content - get instruction based on source
                source_ref = ""
                if idx < len(section_84_test_names): source_ref = "Section 8.4 (Step 1)"
                elif idx < len(section_11_test_names): source_ref = "Section 11 (Test Case Name)"
                
                if source_ref:
                    suggestion_text = f"Synchronize with {source_ref} content."
                else:
                    suggestion_text = "Add technical description."

                all_errors_table.append({
                    "where": where_content, 
                    "what": "test scenario content missing.",
                    "suggestion": suggestion_text,
                    "redirect_text": actual_redirect, 
                    "severity": "High"
                })

        if not section81_has_content:
            all_errors_table.append({
                "where": standard_title, "what": "test scenario content missing.",
                "suggestion": "Add test scenarios.", "redirect_text": actual_redirect, "severity": "High"
            })

    except Exception as e:
        all_errors_table.append({"where": "Section 8.1", "what": f"Error: {e}", "suggestion": "Check JSON format", "severity": "High"})

    # SORTING
    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    def get_sort_key(error):
        where = error.get('where', '')
        if where == standard_title: return (-1, [], severity_order.get(error.get("severity", "Low"), 2))
        match = re.search(r'Test Scenario (\d+)', where)
        if match: return (0, [int(match.group(1))], severity_order.get(error.get("severity", "Low"), 2))
        return (1, [where], severity_order.get(error.get("severity", "Low"), 2))

    all_errors_table.sort(key=get_sort_key)
    
    # Final cleanup of findings
    findings = []
    for err in all_errors_table:
        findings.append({
            "where": err['where'],
            "what": err['what'],
            "suggestion": err['suggestion'],
            "redirect_text": err.get('redirect_text', ''),
            "severity": err.get('severity', 'Low')
        })

    print(json.dumps(findings, indent=4))
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(findings, f, indent=4)
    sys.exit(1 if findings else 0)

if __name__ == "__main__":
    main()
