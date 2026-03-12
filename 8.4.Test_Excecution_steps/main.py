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
        test_id_pattern = re.compile(r'(\d+[\d\.\s]*\d+)') # More inclusive pattern

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

        # 2. Section 8.1 sync removed (Checking individually)
        expected_scenario_ids = []

        # 3. Identify Section 8.4 (Execution Steps)
        standard_title = "8.4. Test Execution Steps"
        redirect_label = "Test Execution Steps"
        target_section = None
        found_title = ""
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            if "execution" in title_lower and "step" in title_lower:
                target_section = section
                found_title = title
                break
        
        if not target_section:
             output_result([{
                "where": standard_title,
                "what": "Section 8.4 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": redirect_label,
                "severity": "High"
            }], 0)

        # Dynamic Display Title based on document's actual numbering
        # Robust prefix match: handles 8.., 8.7, etc. even if stuck to text
        num_match = re.match(r'^([\d\.]+)', found_title)
        has_any_number = num_match is not None
        has_correct_num = found_title.startswith("8.4.")
        
        actual_prefix = num_match.group(1).strip() if num_match else "8.4"
        # Use found prefix for reporting location to reflect document state
        display_title = f"{actual_prefix} {standard_title.split(' ', 1)[1]}"

        if not (has_correct_num and "test execution steps" in found_title.lower()):
            if has_any_number and not has_correct_num:
                # Title body is correct but section number is wrong
                wrong_num = actual_prefix
                all_errors_table.append({
                    "where": display_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '8.4.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '8.4.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            elif not has_any_number:
                # Title body is correct but section number "8.4." is missing entirely
                all_errors_table.append({
                    "where": display_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })

            # Formatting / Space Checks
            if "test execution steps" not in found_title.lower():
                # Detect specific space issues
                is_space_issue = any(part in found_title.lower() for part in ["executionsteps", "testexecution", "8.."])
                what_msg = f"Incorrect formatting (space issue) in the title. Found: '{found_title}'" if is_space_issue else f"Incorrect formatting in the title. Found: '{found_title}'"
                
                all_errors_table.append({
                    "where": display_title,
                    "what": what_msg,
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
        # Process Content
        text_sources = []
        if 'execution_steps' in target_section:
            for item in target_section['execution_steps']:
                if isinstance(item, dict):
                    text_sources.append({'text': item.get('test_scenario', '').strip(), 'steps': item.get('steps', [])})
        
        if 'content' in target_section:
            for item in target_section['content']:
                txt = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                if "test scenario" in txt.lower():
                    text_sources.append({'text': txt, 'steps': []})

        scenario_tracker = {}
        found_id_count = 0

        for source in text_sources:
            text = source['text']
            if not text: continue
            
            m = test_id_pattern.search(text)
            if not m: continue
            
            found_id_count += 1
            found_id = re.sub(r'[\s]+', '', m.group(1))
            
            # Use truth list if available, else fallback to base_id sequence
            if found_id_count <= len(expected_scenario_ids):
                exp_id = expected_scenario_ids[found_id_count - 1]
            else:
                exp_id = f"{base_id}.{found_id_count}" if base_id else found_id
            
            where_ref = f"{display_title} - Test Scenario {exp_id}"
            
            # Format Check (Space issue)
            if "testscenario" in text.lower():
                all_errors_table.append({
                    "where": where_ref,
                    "what": f"Incorrect format: Found '{text.split(':')[0]}' (missing space)",
                    "suggestion": f"Expected: 'Test Scenario {exp_id}:'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })

            # ID Alignment Check
            if found_id != exp_id:
                # Detect if the mismatch is specifically in the base ID part
                found_base = ".".join(found_id.split('.')[:-1]) if '.' in found_id else ""
                error_what = "ID alignment mismatch"
                if base_id and found_base and found_base != base_id:
                    error_what = "ID alignment mismatch (Base ID mismatch)"
                
                all_errors_table.append({
                    "where": where_ref,
                    "what": f"{error_what}: Found '{found_id}', Expected '{exp_id}'",
                    "suggestion": f"Update ID to maintain sequence: '{exp_id}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            
            # Content Check
            has_steps = any(is_meaningful_content(s.get('step', '') if isinstance(s, dict) else str(s)) for s in source['steps'])
            if not has_steps:
                all_errors_table.append({
                    "where": where_ref,
                    "what": f"test scenario content missing. in Test Scenario {exp_id}",
                    "suggestion": f"Add execution steps for Scenario {exp_id}",
                    "redirect_text": found_title,
                    "severity": "High"
                })
            
            scenario_tracker[found_id_count] = True

        # Check for missing scenarios from Section 8.1
        for i, eid in enumerate(expected_scenario_ids, 1):
            if i not in scenario_tracker:
                all_errors_table.append({
                    "where": f"{display_title} - Test Scenario {eid}",
                    "what": f"test scenario content missing. in Test Scenario {eid}",
                    "suggestion": f"Add Section {display_title} details for {eid}",
                    "redirect_text": found_title,
                    "severity": "High"
                })

        if not scenario_tracker and not expected_scenario_ids:
             all_errors_table.append({
                "where": display_title,
                "what": "test scenario content missing.",
                "suggestion": "Add test scenarios and execution steps.",
                "redirect_text": found_title,
                "severity": "High"
            })

    except Exception as e:
        all_errors_table.append({
            "where": "Section 8.4 Processing",
            "what": f"Error: {str(e)}",
            "suggestion": "Check JSON structure",
            "severity": "High"
        })

    # SORTING
    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    def get_sort_key(error):
        where = error.get('where', '')
        if where == display_title: return (-1, [], severity_order.get(error.get("severity", "Low"), 2))
        match = re.search(r'Test Scenario ([\d\.]+)', where)
        if match:
            id_parts = [int(p) for p in match.group(1).split('.') if p.isdigit()]
            return (0, id_parts, severity_order.get(error.get("severity", "Low"), 2))
        return (1, [where], severity_order.get(error.get("severity", "Low"), 2))

    all_errors_table.sort(key=get_sort_key)
    output_result(all_errors_table)

if __name__ == "__main__":
    main()
