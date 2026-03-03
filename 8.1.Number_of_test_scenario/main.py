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
    # Remove common labels and IDs to see if actual description exists
    text = re.sub(r'(Test\s+Sc[eh]n?ario|TC\s*[:.-]|T\.C\.|Test\s+Case)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d+([\. ]+\d+)+\b', '', text) # Remove IDs
    
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
        print(json.dumps([{"where": "System", "what": f"File not found: {json_file}", "severity": "high"}]))
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

        # 1. Get base IDs (Aligned with 8.4 logic but more explicit for cross-check)
        base_id_fp = None
        fp_content = data.get('frontpage_data', {}).get('content', [])
        for item in fp_content:
            m = re.search(r'\b(\d+(?:\s*[\. ]\s*\d+){2})\b', str(item))
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
                        m = re.search(r'\b(\d+(?:\s*[\. ]\s*\d+){2})\b', text.strip())
                        if m: 
                            base_id_sec2 = re.sub(r'[\s]+', '', m.group(1))
                            break
                    if base_id_sec2: break
            if base_id_sec2: break

        # Determine effective base_id for validation (Section 2 is master as requested)
        base_id = base_id_sec2 or base_id_fp
        
        # Report Base ID issues
        expected81_title = "8.1. Number of Test Scenarios"
        if not base_id:
            all_errors_table.append({
                'where': f"{expected81_title}:",
                'what': "Base ID missing: Could not find valid ID (e.g., 1.1.2) in Section 2 or Front Page.",
                'suggestion': "Ensure Section 2 or the Front Page contains the Requirement ID.",
                'severity': 'high'
            })
        elif base_id_fp and base_id_sec2 and base_id_sec2 != base_id_fp:
            all_errors_table.append({
                'where': f"{expected81_title}:",
                'what': f"Base ID mismatch: Section 2 shows '{base_id_sec2}' but Front Page shows '{base_id_fp}'.",
                'suggestion': "Ensure the Requirement ID is consistent throughout the document.",
                'severity': 'medium'
            })

        # 2. Check for Section 8.1
        section81_found = False
        section81_has_content = False
        expected81_title = "8.1. Number of Test Scenarios"
        redirect_title = "Number of Test Scenarios"
        
        for section in sections:
            title = section.get('title', '').strip()
            sec_id = section.get('section_id', '')

            if sec_id == 'SEC-09' or re.search(r'8\.1|Number\s+of\s+Test\s+Scenarios', title, re.IGNORECASE):
                section81_found = True
                
                # Title Validation
                if title.replace(':', '').strip().lower() != expected81_title.replace(':', '').strip().lower():
                    all_errors_table.append({
                        'where': f"{expected81_title}:",
                        'what': f"Incorrect title: Found '{title}'",
                        'suggestion': f"Change title to exactly '{expected81_title}:'",
                        'redirect_text': redirect_title,
                        'severity': 'medium'
                    })
                
                # Use redirect title from actual if possible for consistency
                actual_redirect = re.sub(r'^\d+\.\d?\.\s*', '', title).strip().replace(':', '') or redirect_title

                # Process Content
                scenario_tracker = {}
                position = 0
                
                # Normalize data sources (test_scenarios or content)
                scenarios_in_json = section.get('test_scenarios', [])
                content_items = section.get('content', [])
                
                parsed_scenarios = []
                if scenarios_in_json:
                    # STRUCTURED MODE: Each item is one scenario
                    for item in scenarios_in_json:
                        if isinstance(item, dict):
                            id_text = item.get('test_scenario', '').strip()
                            desc_text = item.get('description', '').strip()
                            parsed_scenarios.append({'header': id_text, 'desc': desc_text})
                        else:
                            parsed_scenarios.append({'header': str(item).strip(), 'desc': ''})
                else:
                    # UNSTRUCTURED MODE: Split by ID pattern
                    raw_text_blocks = []
                    for item in content_items:
                        txt = item.get('text', '') if isinstance(item, dict) else str(item)
                        if txt.strip(): raw_text_blocks.append(txt.strip())
                    
                    # Joining and re-splitting to handle IDs correctly
                    full_text = " ".join(raw_text_blocks)
                    parts = re.split(r'(?=\b\d+(?:\s*[\. ]\s*\d+){3}\b)', full_text)
                    for p in parts:
                        p = p.strip()
                        if not p: continue
                        m = test_id_pattern.search(p)
                        if m:
                            raw_id = m.group(1)
                            id_pos = p.find(raw_id)
                            header = p[:id_pos+len(raw_id)].strip()
                            desc = p[id_pos+len(raw_id):].strip()
                            parsed_scenarios.append({'header': header, 'desc': desc})
                        else:
                            # If no ID but text exists, maybe it belongs to previous or is a loose block
                            if parsed_scenarios:
                                parsed_scenarios[-1]['desc'] += " " + p
                            else:
                                parsed_scenarios.append({'header': '', 'desc': p})

                for sc in parsed_scenarios:
                    header = sc['header']
                    desc = sc['desc']
                    full_sc_text = header + " " + desc

                    # Check for missing space in 'Test Scenario'
                    if re.search(r'TestScenario', full_sc_text, re.IGNORECASE):
                        all_errors_table.append({
                            'where': f"{expected81_title}: - Test Scenario {position + 1}",
                            'what': "Incorrect format: Found 'TestScenario' (missing space)",
                            'suggestion': "Expected: 'Test Scenario'",
                            'redirect_text': actual_redirect,
                            'severity': 'low'
                        })
                    
                    matches = test_id_pattern.findall(full_sc_text)
                    if not matches:
                        # Check labels if no numeric ID found
                        if any(l in (header + " " + desc).lower() for l in ['test scenario', 'tc', 'test case']):
                            section81_has_content = True
                            position += 1
                            exp_id = f"{base_id}.{position}" if base_id else f"X.{position}"
                            where_ref = f"8.1. Number of Test Scenarios: - Test Scenario {exp_id}"
                            
                            all_errors_table.append({
                                'where': where_ref,
                                'what': f"ID missing in content. in Test Scenario {exp_id}",
                                'suggestion': f"Expected: 'Test Scenario {exp_id}: [Description]'",
                                'redirect_text': actual_redirect,
                                'severity': 'medium'
                            })
                        continue
                    
                    section81_has_content = True
                    # In structured mode, we expect exactly 1 ID per block
                    # If we found multiple in a single 'desc', we treat the first one as the primary
                    raw_id = matches[0]
                    test_id = re.sub(r'[\s]+', '', raw_id)
                    position += 1
                    exp_id = f"{base_id}.{position}" if base_id else test_id
                    where_ref = f"8.1. Number of Test Scenarios: - Test Scenario {exp_id}"
                    
                    # Content Check (Consolidated)
                    # For Section 8.1, content is the description
                    # Clean the ID/Label part from the beginning of the header/desc block
                    combined = (header + " " + desc).strip()
                    id_idx = combined.find(raw_id)
                    content_after_id = combined[id_idx + len(raw_id):].strip()
                    content_after_id = re.sub(r'^[:\.\s]+', '', content_after_id)
                    
                    has_meaningful_content = is_meaningful_content(content_after_id)
                    
                    # Reporting (Aligned with 8.4)
                    if not has_meaningful_content:
                        all_errors_table.append({
                            'where': where_ref,
                            'what': f"test scenario content missing. in Test Scenario {exp_id}",
                            'suggestion': f"Add description for Scenario {exp_id}",
                            'redirect_text': actual_redirect,
                            'severity': 'high'
                        })
                    
                    # Sequence/Alignment
                    if test_id != exp_id:
                        if base_id and ".".join(test_id.split(".")[:3]) != base_id:
                             all_errors_table.append({
                                'where': where_ref,
                                'what': f"Base ID mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                                'suggestion': f"Expected Base ID: {base_id}",
                                'redirect_text': actual_redirect,
                                'severity': 'low'
                            })
                        else:
                            all_errors_table.append({
                                'where': where_ref,
                                'what': f"ID alignment mismatch: Found '{test_id}'. in Test Scenario {exp_id}",
                                'suggestion': f"Correct ID to {exp_id}",
                                'redirect_text': actual_redirect,
                                'severity': 'low'
                            })
                break

        if not section81_found:
            all_errors_table.append({'where': expected81_title + ":", 'what': "Section 8.1 missing", 'suggestion': f"Add Section {expected81_title}:", 'severity': 'high'})
        elif not section81_has_content:
            all_errors_table.append({'where': expected81_title + ":", 'what': "test scenario content missing. in 8.1. Number of Test Scenarios", 'suggestion': "Add test scenarios.", 'redirect_text': redirect_title, 'severity': 'high'})

    except Exception as e:
        all_errors_table.append({'where': "Section 8.1 Processing", 'what': f"Error: {str(e)}", 'suggestion': "Check JSON format", 'severity': 'high'})

    # Sorting (Natural Sort by Scenario ID)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    
    def get_sort_key(error):
        where = error.get('where', '')
        # Handle Section title/missing errors first
        if where.endswith(':'):
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

    # Final Output
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
