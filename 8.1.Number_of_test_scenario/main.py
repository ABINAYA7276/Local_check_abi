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

        # 1. Get base IDs (Aligned with 8.4 logic)
        base_id_fp = None
        fp_content = data.get('frontpage_data', {}).get('content', [])
        for item in fp_content:
            m = re.search(r'(\d+(?:\s*[\. ]\s*\d+){2})', str(item))
            if m:
                base_id_fp = re.sub(r'[\s]+', '', m.group(1))
                break
        
        base_id_sec2 = None
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
                        m = re.search(r'(\d+(?:\s*[\. ]\s*\d+){2})', text.strip())
                        if m: 
                            base_id_sec2 = re.sub(r'[\s]+', '', m.group(1))
                            break
                    if base_id_sec2: break
            if base_id_sec2: break
        
        base_id = base_id_sec2 or base_id_fp
        standard_title = "8.1. Number of Test Scenarios"
        redirect_stable = "Number of Test Scenarios"
        
        # 2. Check for Section 8.1 Identification
        target_section = None
        for section in sections:
            title = section.get('title', '').strip().replace('\n', ' ')
            title_lower = title.lower()
            if 'number' in title_lower and 'test' in title_lower and 'scenario' in title_lower:
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
        # print(f"DEBUG: Found Title: {found_title}")
        title_lower = found_title.lower()

        # 3. TITLE VALIDATION
        has_body = 'number' in title_lower and 'test' in title_lower and 'scenario' in title_lower
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("8.1.")

        if not (has_correct_num and has_body):
            if has_body and has_any_number and not has_correct_num:
                wrong_num = num_prefix_match.group(1).strip()
                all_errors_table.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '8.1.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '8.1.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif has_body and not has_any_number:
                all_errors_table.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })
            else:
                # If we have the body, we proceed. If not, missing.
                return print(json.dumps([{
                    "where": standard_title,
                    "what": "Section 8.1 missing",
                    "suggestion": f"Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "High"
                }], indent=4))

        # 4. CONTENT VALIDATION
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
                    # Aggregate strings/lists
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
                    raw_id = m.group(1)
                    id_pos = p.find(raw_id)
                    parsed_scenarios.append({'header': p[:id_pos+len(raw_id)].strip(), 'desc': p[id_pos+len(raw_id):].strip()})
                else:
                    if parsed_scenarios: parsed_scenarios[-1]['desc'] += " " + p
                    else: parsed_scenarios.append({'header': '', 'desc': p})

        # Validate parsed scenarios
        for item in parsed_scenarios:
            position += 1
            section81_has_content = True
            header = item['header']
            desc = item['desc']
            combined = (header + " " + desc).strip()
            id_match = test_id_pattern.search(combined)
            
            exp_id = f"{base_id}.{position}" if base_id else f"[ID].{position}"
            where_ref = f"{standard_title} - Test Scenario {position}"

            # Space Check
            if re.search(r'TestScenario', header, re.IGNORECASE):
                all_errors_table.append({
                    "where": where_ref, "what": f"Incorrect format: Found 'TestScenario' (missing space)",
                    "suggestion": "Expected: 'Test Scenario'", "redirect_text": actual_redirect, "severity": "Low"
                })

            if not id_match:
                all_errors_table.append({
                    "where": where_ref, "what": f"test scenario ID missing. Found: '{header[:30]}'",
                    "suggestion": f"Expected: 'Test Scenario {exp_id}:'", "redirect_text": actual_redirect, "severity": "High"
                })
                continue

            found_id_raw = id_match.group(1)
            found_id = re.sub(r'[\s]+', '', found_id_raw)
            # Alignment Check
            if base_id and not found_id.startswith(base_id):
                all_errors_table.append({
                    "where": where_ref, "what": f"Base ID mismatch: Found '{found_id}'.",
                    "suggestion": f"Expected Base ID: {base_id}", "redirect_text": actual_redirect, "severity": "Low"
                })
            elif found_id != exp_id:
                all_errors_table.append({
                    "where": where_ref, "what": f"ID alignment mismatch: Found '{found_id}'.",
                    "suggestion": f"Expected: {exp_id}", "redirect_text": actual_redirect, "severity": "Low"
                })

            # Content Check
            clean_desc = re.sub(r'^[:.\s]+', '', desc)
            if not is_meaningful_content(clean_desc):
                all_errors_table.append({
                    "where": where_ref, "what": f"test scenario content missing. Found ID '{found_id_raw}'.",
                    "suggestion": f"Add description for Test Scenario {found_id}", "redirect_text": actual_redirect, "severity": "High"
                })

        if not section81_has_content:
            all_errors_table.append({
                "where": standard_title, "what": "test scenario content missing. in 8.1. Number of Test Scenarios:",
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
