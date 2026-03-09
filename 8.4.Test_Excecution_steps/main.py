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

def main():
    parser = argparse.ArgumentParser(description="Validate Section 8.4: Test Execution Steps.")
    parser.add_argument("json_file", type=str, help="Path to the structured JSON file")
    
    args = parser.parse_args()
    json_file = Path(args.json_file)
    
    if not json_file.is_file():
        print(f"Error: Path is not a file - {json_file}")
        sys.exit(1)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
        
    json_path = str(json_file)
    def output_result(findings, exit_code=0):
        print(json.dumps(findings, indent=4))
        try:
            with open('output.json', 'w', encoding='utf-8') as f:
                json.dump(findings, f, indent=4)
        except:
            pass
        sys.exit(exit_code)

    try:
        all_errors_table = []
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        test_id_pattern = re.compile(r'\b(\d+(?:\s*[\. ]\s*\d+){3})\b')

        # 1. Get base ID
        base_id = None
        fp_content = data.get('frontpage_data', {}).get('content', [])
        for item in fp_content:
            m = re.search(r'\b(\d+(?:\s*[\. ]\s*\d+){2})\b', str(item))
            if m:
                base_id = re.sub(r'[\s]+', '', m.group(1))
                break
        
        if not base_id:
            for section in sections:
                title = section.get('title', '').strip()
                # Robust identification: Look for "2. Security Requirement" or "3. Requirement Description"
                if re.search(r'\b[23]\.', title) and "requirement" in title.lower():
                    fields = ['security_requirement', 'itsar_section_details', 'content']
                    for field in fields:
                        val = section.get(field, '')
                        if not val: continue
                        vals = val if isinstance(val, list) else [val]
                        for v in vals:
                            text = v.get('text', '') if isinstance(v, dict) else str(v)
                            m = re.search(r'\b(\d+(?:\s*[\. ]\s*\d+){2})\b', text.strip())
                            if m: 
                                base_id = re.sub(r'[\s]+', '', m.group(1))
                                break
                        if base_id: break
                if base_id: break

        # 2. Get expected IDs from Section 8.1 (Source of Truth)
        expected_scenario_ids = []
        for section in sections:
            title = section.get('title', '').strip()
            # Look for 8.1 and keywords like "scenario" or "number"
            if "8.1" in title and ("scenario" in title.lower() or "number" in title.lower()):
                scenarios = section.get('test_scenarios', [])
                if isinstance(scenarios, list):
                    for s in scenarios:
                        s_text = s.get('test_scenario', '') if isinstance(s, dict) else str(s)
                        m = test_id_pattern.search(s_text)
                        if m:
                            expected_scenario_ids.append(re.sub(r'[\s]+', '', m.group(1)))
                break

        # 3. Check for Section 8.4
        section84_found = False
        section84_has_content = False
        expected84_title = "8.4. Test Execution Steps"
        redirect_title = "Test Execution Steps"
        
        # IDENTIFICATION SUCCESSFUL
        found_title = ""
        target_section = None
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            if "execution" in title_lower and "step" in title_lower:
                target_section = section
                found_title = title
                break
        
        if not target_section:
             output_result([{
                "where": expected84_title,
                "what": "Section 8.4 missing",
                "suggestion": f"Expected: '{expected84_title}'",
                "redirect_text": redirect_title,
                "severity": "High"
            }], 0)

        # 3. TITLE VALIDATION
        title_lower = found_title.lower()
        has_body = "execution" in title_lower and "step" in title_lower
        
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("8.4.")

        if not (has_correct_num and has_body):
            if has_body and has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = num_prefix_match.group(1).strip()
                all_errors_table.append({
                    "where": expected84_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '8.4.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '8.4.'. Expected: '{expected84_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_body and not has_any_number:
                # Title body is correct but section number "8.4." is missing entirely
                all_errors_table.append({
                    "where": expected84_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{expected84_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })
            else:
                # Title is entirely wrong or absent
                return output_result([{
                    "where": expected84_title,
                    "what": "Section 8.4 missing",
                    "suggestion": f"Expected: '{expected84_title}'",
                    "redirect_text": found_title,
                    "severity": "High"
                }], 0)
            # Proceed with content check
        section84_found = True
        section = target_section
        actual_title = found_title
        # Clean redirect: Remove leading numbers and trailing colons
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or redirect_title
                
        text_sources = []
        if 'execution_steps' in section:
            for item in section['execution_steps']:
                if isinstance(item, dict):
                    text_sources.append({
                        'text': item.get('test_scenario', '').strip(),
                        'steps': item.get('steps', [])
                    })
        
        if 'content' in section:
            for item in section['content']:
                txt = ""
                if isinstance(item, dict) and item.get('type') == 'paragraph': txt = item.get('text', '').strip()
                elif isinstance(item, str): txt = item.strip()
                if txt: text_sources.append({'text': txt, 'steps': []})

        scenario_tracker = {}
        found_id_count = 0

        for source in text_sources:
            text = source['text']
            if not text: continue
            
            matches = test_id_pattern.findall(text)
            if not matches: continue
            
            section84_has_content = True
            # Check for missing space in 'Test Scenario'
            if re.search(r'TestScenario', text, re.IGNORECASE):
                all_errors_table.append({
                    'where': f"{expected84_title} - Test Scenario {found_id_count + 1 if base_id else 'Content'}",
                    'what': "Incorrect format: Found 'TestScenario' (missing space)",
                    'suggestion': "Expected: 'Test Scenario'",
                    'redirect_text': redirect_val,
                    'severity': 'Low'
                })

            for raw_id in matches:
                test_id = re.sub(r'[\s]+', '', raw_id)
                id_pos = text.find(raw_id)
                found_id_count += 1
                
                # Use Base ID + current position as the expectation
                exp_id = f"{base_id}.{found_id_count}" if base_id else test_id
                where_ref = f"{expected84_title} - Test Scenario {exp_id}"
                
                if found_id_count not in scenario_tracker:
                    scenario_tracker[found_id_count] = {
                        'has_any_content': False,
                        'expected_id': exp_id,
                        'test_id': test_id,
                        'where': where_ref,
                        'errors': []
                    }
                
                suffix = text[id_pos + len(raw_id):].strip()
                clean_suffix = re.sub(r'^[:\.\s]+', '', suffix)
                if is_meaningful_content(clean_suffix):
                    scenario_tracker[found_id_count]['has_any_content'] = True

                steps = source.get('steps', [])
                if steps:
                    for step_item in steps:
                        step_content = step_item.get('step', '').strip() if isinstance(step_item, dict) else str(step_item).strip()
                        if is_meaningful_content(step_content):
                            scenario_tracker[found_id_count]['has_any_content'] = True
                            break
                
                if test_id != exp_id:
                    is_base_mismatch = base_id and not test_id.startswith(base_id)
                    if is_base_mismatch:
                        scenario_tracker[found_id_count]['errors'].append({
                            'where': where_ref,
                            'what': f"Base ID mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                            'suggestion': f"Expected Base ID: {base_id}",
                            'redirect_text': redirect_val,
                            'severity': 'Low'
                        })
                    
                    scenario_tracker[found_id_count]['errors'].append({
                        'where': where_ref,
                        'what': f"Alignment mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                        'suggestion': f"Expected: {exp_id}",
                        'redirect_text': redirect_val,
                        'severity': 'Low'
                    })

        # Ensure all expected scenarios from Section 8.1 are checked even if not found
        total_expected = max(len(expected_scenario_ids), found_id_count)
        for i in range(1, total_expected + 1):
            if i not in scenario_tracker:
                eid = expected_scenario_ids[i-1] if i <= len(expected_scenario_ids) else (f"{base_id}.{i}" if base_id else f"Slot {i}")
                where = f"{expected84_title} - Test Scenario {eid}"
                all_errors_table.append({
                    'where': where,
                    'what': f"test scenario content missing. in Test Scenario {eid}",
                    'suggestion': f"Add description or execution steps for Scenario {eid}",
                    'redirect_text': redirect_val,
                    'severity': 'High'
                })
            else:
                data = scenario_tracker[i]
                if not data['has_any_content']:
                    all_errors_table.append({
                        'where': data['where'],
                        'what': f"test scenario content missing. in Test Scenario {data['expected_id']}",
                        'suggestion': f"Add description or execution steps to provide content for Scenario {data['expected_id']}",
                        'redirect_text': redirect_val,
                        'severity': 'High'
                    })
                for err in data['errors']:
                    all_errors_table.append(err)
                
                break

        if not section84_found:
             all_errors_table.append({'where': expected84_title, 'what': "Section 8.4 missing", 'suggestion': f"Add Section {expected84_title}", 'severity': 'High'})
        elif not section84_has_content:
            all_errors_table.append({'where': expected84_title, 'what': "test scenario content missing. in 8.4. Test Execution Steps", 'suggestion': "Add test scenarios.", 'redirect_text': redirect_title, 'severity': 'High'})
            
    except Exception as e:
        all_errors_table.append({'where': "Section 8.4 Processing", 'what': f"Error: {str(e)}", 'suggestion': "Check JSON format", 'severity': 'High'})

    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    
    def get_sort_key(error):
        where = error.get('where', '')
        # Handle Section 8.4 title/missing errors first
        if where == expected84_title:
            return (-1, [], severity_order.get(error.get("severity", "Low"), 2))
            
        # Extract scenario ID for natural sorting (e.g., 1.1.1.2 before 1.1.1.10)
        match = re.search(r'Test Scenario ([\d\s\.]+)', where)
        if match:
            id_str = match.group(1).replace(' ', '')
            id_parts = [int(x) for x in id_str.split('.') if x.strip().isdigit()]
            return (0, id_parts, severity_order.get(error.get("severity", "Low"), 2))
            
        # Fallback for any other errors
        return (1, [where], severity_order.get(error.get("severity", "Low"), 2))

    all_errors_table.sort(key=get_sort_key)

    findings = []
    for error in all_errors_table:
        findings.append({
            "where": error['where'],
            "what": error['what'],
            "suggestion": error['suggestion'],
            "redirect_text": error.get('redirect_text', ''),
            "severity": error.get('severity', 'Low')
        })

    print(json.dumps(findings, indent=4))
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(findings, f, indent=4)
    sys.exit(1 if findings else 0)

if __name__ == "__main__":
    main()
