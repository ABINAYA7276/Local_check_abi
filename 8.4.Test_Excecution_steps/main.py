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
    all_errors_table = []
    
    try:
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
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            # Look for 8.4 and keywords like "execution" or "steps"
            if "8.4" in title and ("execution" in title_lower or "steps" in title_lower):
                section84_found = True
                
                # Title Validation
                if title.replace(':', '').strip().lower() != expected84_title.replace(':', '').strip().lower():
                    all_errors_table.append({
                        'where': actual_title if 'actual_title' in locals() else expected84_title,
                        'what': f"Incorrect title: Found '{title}'",
                        'suggestion': f"Change title to exactly '{expected84_title}'",
                        'redirect_text': redirect_title,
                        'severity': 'medium'
                    })
                
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
                            'redirect_text': redirect_title,
                            'severity': 'low'
                        })

                    for raw_id in matches:
                        test_id = re.sub(r'[\s]+', '', raw_id)
                        id_pos = text.find(raw_id)
                        found_id_count += 1
                        
                        # User wants individual check based on sequence position (1, 2, 3...)
                        # Use Base ID + current position as the expectation
                        exp_id = f"{base_id}.{found_id_count}" if base_id else test_id
                        where_ref = f"{expected84_title} - Test Scenario {exp_id}"
                        
                        # Track errors per sequence position
                        if found_id_count not in scenario_tracker:
                            scenario_tracker[found_id_count] = {
                                'has_any_content': False,
                                'expected_id': exp_id,
                                'test_id': test_id,
                                'where': where_ref,
                                'errors': []
                            }
                        
                        # Content Validation for this specific instance
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
                        
                        # Alignment Validation for this specific instance
                        if test_id != exp_id:
                            # 1. Base ID Check
                            is_base_mismatch = base_id and not test_id.startswith(base_id)
                            if is_base_mismatch:
                                scenario_tracker[found_id_count]['errors'].append({
                                    'where': where_ref,
                                    'what': f"Base ID mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                                    'suggestion': f"Expected Base ID: {base_id}",
                                    'redirect_text': redirect_title,
                                    'severity': 'low'
                                })
                            
                            # 2. Sequence/Alignment Check (against 1.1.1.x or 8.1 IDs)
                            # We report an alignment mismatch if the ID is not exactly what was expected
                            scenario_tracker[found_id_count]['errors'].append({
                                'where': where_ref,
                                'what': f"Alignment mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                                'suggestion': f"Expected: {exp_id}",
                                'redirect_text': redirect_title,
                                'severity': 'low'
                            })

                # Ensure all expected scenarios from Section 8.1 are checked even if not found
                total_expected = max(len(expected_scenario_ids), found_id_count)
                for i in range(1, total_expected + 1):
                    if i not in scenario_tracker:
                        eid = expected_scenario_ids[i-1] if i <= len(expected_scenario_ids) else f"{base_id}.{i}"
                        where = f"{expected84_title} - Test Scenario {eid}"
                        all_errors_table.append({
                            'where': where,
                            'what': f"test scenario content missing. in Test Scenario {eid}",
                            'suggestion': f"Add description or execution steps for Scenario {eid}",
                            'redirect_text': redirect_title,
                            'severity': 'high'
                        })
                    else:
                        data = scenario_tracker[i]
                        # Report content missing for the slots that were found but were empty
                        if not data['has_any_content']:
                            all_errors_table.append({
                                'where': data['where'],
                                'what': f"test scenario content missing. in Test Scenario {data['expected_id']}",
                                'suggestion': f"Add description or execution steps to provide content for Scenario {data['expected_id']}",
                                'redirect_text': redirect_title,
                                'severity': 'high'
                            })
                        # Add any individual alignment errors found for this slot
                        for err in data['errors']:
                            all_errors_table.append(err)
                
                break

        if not section84_found:
             all_errors_table.append({'where': expected84_title, 'what': "Section 8.4 missing", 'suggestion': f"Add Section {expected84_title}", 'severity': 'high'})
        elif not section84_has_content:
            all_errors_table.append({'where': expected84_title, 'what': "test scenario content missing. in 8.4. Test Execution Steps", 'suggestion': "Add test scenarios.", 'redirect_text': redirect_title, 'severity': 'high'})
            
    except Exception as e:
        all_errors_table.append({'where': "Section 8.4 Processing", 'what': f"Error: {str(e)}", 'suggestion': "Check JSON format", 'severity': 'high'})

    severity_order = {"high": 0, "medium": 1, "low": 2}
    
    def get_sort_key(error):
        where = error.get('where', '')
        # Handle Section 8.4 title/missing errors first
        if where == expected84_title:
            return (-1, [], severity_order.get(error.get("severity", "low"), 2))
            
        # Extract scenario ID for natural sorting (e.g., 1.1.1.2 before 1.1.1.10)
        match = re.search(r'Test Scenario ([\d\s\.]+)', where)
        if match:
            id_str = match.group(1).replace(' ', '')
            id_parts = [int(x) for x in id_str.split('.') if x.strip().isdigit()]
            return (0, id_parts, severity_order.get(error.get("severity", "low"), 2))
            
        # Fallback for any other errors
        return (1, [where], severity_order.get(error.get("severity", "low"), 2))

    all_errors_table.sort(key=get_sort_key)

    findings = []
    for error in all_errors_table:
        findings.append({
            "where": error['where'],
            "what": error['what'],
            "suggestion": error['suggestion'],
            "redirect_text": error.get('redirect_text', ''),
            "severity": error.get('severity', 'low')
        })

    print(json.dumps(findings, indent=4))
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(findings, f, indent=4)
    sys.exit(1 if findings else 0)

if __name__ == "__main__":
    main()
