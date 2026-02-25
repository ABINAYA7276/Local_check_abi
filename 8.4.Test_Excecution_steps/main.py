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
                sec_id = section.get('section_id', '')
                if sec_id in ['SEC-01', 'SEC-02'] or re.search(r'2\.\s+Security Requirement', title, re.IGNORECASE):
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

        # 2. Check for Section 8.4
        section84_found = False
        section84_has_content = False
        expected84_title = "8.4. Test Execution Steps"
        redirect_title = "Test Execution Steps"
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            sec_id = section.get('section_id', '')

            if sec_id == 'SEC-12' or (("8.4" in title) and ("execution" in title_lower or "steps" in title_lower)):
                section84_found = True
                
                # Title Validation
                if title.replace(':', '').strip().lower() != expected84_title.replace(':', '').strip().lower():
                    all_errors_table.append({
                        'where': expected84_title,
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

                position = 0
                scenario_tracker = {}

                for source in text_sources:
                    text = source['text']
                    if not text: continue
                    
                    matches = test_id_pattern.findall(text)
                    if not matches: continue
                    
                    section84_has_content = True
                    for raw_id in matches:
                        test_id = re.sub(r'[\s]+', '', raw_id)
                        id_pos = text.find(raw_id)
                        position += 1
                        exp_id = f"{base_id}.{position}" if base_id else test_id
                        where_ref = f"{expected84_title} - Test Scenario {exp_id}"
                        
                        if test_id not in scenario_tracker:
                            scenario_tracker[test_id] = {
                                'has_any_content': False,
                                'expected_id': exp_id,
                                'raw_id': raw_id,
                                'where': where_ref,
                                'id_error': None
                            }
                        
                        # Unit Content Check: Check Description and all steps as a single "block"
                        suffix = text[id_pos + len(raw_id):].strip()
                        clean_suffix = re.sub(r'^[:\.\s]+', '', suffix)
                        if is_meaningful_content(clean_suffix):
                            scenario_tracker[test_id]['has_any_content'] = True

                        steps = source.get('steps', [])
                        if steps:
                            for step_item in steps:
                                step_content = step_item.get('step', '').strip() if isinstance(step_item, dict) else str(step_item).strip()
                                if is_meaningful_content(step_content):
                                    scenario_tracker[test_id]['has_any_content'] = True
                                    break # One piece of content is enough to prove "presence"
                        
                        # Maintain ID sequence check (Alignment/Base ID)
                        if test_id != exp_id:
                            if base_id and ".".join(test_id.split(".")[:3]) != base_id:
                                scenario_tracker[test_id]['id_error'] = {
                                    'where': where_ref,
                                    'what': f"Base ID mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                                    'suggestion': f"Expected Base ID: {base_id}",
                                    'redirect_text': redirect_title,
                                    'severity': 'low'
                                }
                            else:
                                scenario_tracker[test_id]['id_error'] = {
                                    'where': where_ref,
                                    'what': f"ID alignment mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                                    'suggestion': f"Correct ID to {exp_id}",
                                    'redirect_text': redirect_title,
                                    'severity': 'low'
                                }

                # FINAL CONSOLIDATION
                for tid, data in scenario_tracker.items():
                    where = data['where']
                    eid = data['expected_id']
                    
                    # Single Content Requirement: Scenario is either "Present" or "Missing"
                    if not data['has_any_content']:
                        all_errors_table.append({
                            'where': where,
                            'what': f"test scenario content missing. in Test Scenario {eid}",
                            'suggestion': f"Add description or execution steps to provide content for Scenario {eid}",
                            'redirect_text': redirect_title,
                            'severity': 'high'
                        })
                    
                    # Still report sequence/alignment issues at low severity
                    if data['id_error']:
                         all_errors_table.append(data['id_error'])
                
                break

        if not section84_found:
             all_errors_table.append({'where': expected84_title, 'what': "Section 8.4 missing", 'suggestion': f"Add Section {expected84_title}", 'severity': 'high'})
        elif not section84_has_content:
            all_errors_table.append({'where': expected84_title, 'what': "test scenario content missing. in 8.4. Test Execution Steps", 'suggestion': "Add test scenarios.", 'redirect_text': redirect_title, 'severity': 'high'})
            
    except Exception as e:
        all_errors_table.append({'where': "Section 8.4 Processing", 'what': f"Error: {str(e)}", 'suggestion': "Check JSON format", 'severity': 'high'})

    severity_order = {"high": 0, "medium": 1, "low": 2}
    all_errors_table.sort(key=lambda x: (severity_order.get(x.get("severity", "low"), 2), x.get("where", "")))

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
