import sys
import json
import re
from pathlib import Path

def is_meaningful_content(text: str) -> bool:
    if not text: return False
    text = text.strip().lower()
    if text == 'na': return True
    if text in ['none', 'n/a', 'nil', '.', '-', '_', '...'] or len(text) < 3: return False
    if all(c in '.-_,;:!? ' for c in text): return False
    return True

def main():
    if len(sys.argv) < 2:
        print(json.dumps([{"where": "System", "what": "No JSON file specified", "severity": "high"}]))
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    if not json_path.is_file():
        print(json.dumps([{"where": "System", "what": f"File not found: {json_path}", "severity": "high"}]))
        sys.exit(1)

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        test_id_pattern = re.compile(r'\b(\d+(?:\s*[. ]\s*\d+){3})\b')

        # 1. Get base IDs (Aligned with 8.1/8.4 logic)
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

        # Determine effective base_id for validation (Section 2 is master)
        base_id = base_id_sec2 or base_id_fp
        
        all_errors = []
        expected9_title = "9. Expected Results for Pass:"
        redirect_title = "Expected Results for Pass"


        # Find Section 9
        target_section = None
        for sec in sections:
            title = sec.get('title', '').strip()
            sec_id = sec.get('section_id', '')
            if sec_id == 'SEC-13' or re.search(r'9\.\s+Expected\s+Result', title, re.IGNORECASE):
                target_section = sec
                break

        if not target_section:
            all_errors.append({
                "pos": 0,
                "where": expected9_title, 
                "what": "Section 9 missing", 
                "suggestion": f"Add {expected9_title}", 
                "severity": "high"
            })
        else:
            actual_title = target_section.get('title', '').strip()
            if actual_title.replace(':', '').strip().lower() != expected9_title.replace(':', '').strip().lower():
                all_errors.append({
                    'pos': 0,
                    'where': expected9_title,
                    'what': f"Incorrect title: Found '{actual_title}'",
                    'suggestion': f"Change title to exactly '{expected9_title}'",
                    'redirect_text': redirect_title,
                    'severity': 'medium'
                })

            actual_redirect = re.sub(r'^\d+\.\d?\.\s*', '', actual_title).strip().replace(':', '') or redirect_title

            # Normalize data sources
            er_items = target_section.get('expected_results', [])
            content_items = target_section.get('content', [])

            parsed_scenarios = []
            if er_items:
                # STRUCTURED MODE: List of dicts with test_case_id and expected_result
                for x in er_items:
                    if isinstance(x, dict):
                        # Use Master Logic to handle strings or lists
                        h_val = x.get('test_case_id', '')
                        if isinstance(h_val, list):
                            h = " ".join([str(i) for i in h_val if i]).strip()
                        else:
                            h = str(h_val).strip()
                            
                        d_val = x.get('expected_result', '')
                        if isinstance(d_val, list):
                            d = " ".join([str(i) for i in d_val if i]).strip()
                        else:
                            d = str(d_val).strip()
                            
                        parsed_scenarios.append({'header': h, 'desc': d})
                    else:
                        parsed_scenarios.append({'header': str(x).strip(), 'desc': ''})
            else:
                # UNSTRUCTURED MODE: Split content by ID pattern
                raw_text_blocks = []
                for item in content_items:
                    txt = item.get('text', '') if isinstance(item, dict) else str(item)
                    if txt.strip(): raw_text_blocks.append(txt.strip())
                
                full_text = " ".join(raw_text_blocks)
                parts = re.split(r'(?=\b\d+(?:\s*[. ]\s*\d+){3}\b)', full_text)
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
                        if parsed_scenarios:
                            parsed_scenarios[-1]['desc'] += " " + p
                        else:
                            parsed_scenarios.append({'header': '', 'desc': p})

            # Validate each scenario
            position = 0
            for item in parsed_scenarios:
                position += 1
                header = item['header']
                desc = item['desc']
                
                # Check for ID in header or beginning of desc
                combined = (header + " " + desc).strip()
                
                # Check for missing space in 'Test Scenario' field/header only
                if re.search(r'TestScenario', header, re.IGNORECASE):
                    all_errors.append({
                        'pos': position,
                        'where': f"{expected9_title} - Test Scenario {position}",
                        'what': "Incorrect format: Found 'TestScenario' (missing space)",
                        'suggestion': "Expected: 'Test Scenario'",
                        'redirect_text': actual_redirect,
                        'severity': 'low'
                    })

                id_match = test_id_pattern.search(combined)
                
                exp_id = f"{base_id}.{position}" if base_id else f"X.X.X.{position}"
                
                # Check for ID in header or beginning of desc
                combined = (header + " " + desc).strip()
                id_match = test_id_pattern.search(combined)
                
                raw_id_text = id_match.group(1) if id_match else "Missing ID"
                found_id = re.sub(r'[\s]+', '', raw_id_text) if id_match else "Missing"
                
                where_ref = f"{expected9_title} - Test Scenario {position}"

                if not id_match:
                    all_errors.append({
                        "pos": position,
                        "where": where_ref, 
                        "what": f"ID missing in test scenario {position}", 
                        "suggestion": f"Expected: 'Test Scenario {exp_id}:'", 
                        "redirect_text": actual_redirect, 
                        "severity": "medium"
                    })
                    continue
                
                # Check 1: Base ID Mismatch
                found_parts = found_id.split('.')
                found_base = ".".join(found_parts[:3]) if len(found_parts) >= 3 else found_id
                
                if base_id and found_base != base_id:
                    all_errors.append({
                        "pos": position,
                        "where": where_ref, 
                        "what": f"Base ID is incorrect. Found '{found_base}'.", 
                        "suggestion": f"Expected Base ID: {base_id}", 
                        "redirect_text": actual_redirect, 
                        "severity": "low"
                    })

                # Check 2: Sequence Alignment
                found_seq = found_parts[-1] if found_parts else ""
                expected_seq = str(position)
                if found_seq != expected_seq:
                    all_errors.append({
                        "pos": position,
                        "where": where_ref, 
                        "what": f"ID alignment is incorrect. Found '{found_id}'.", 
                        "suggestion": f"Correct alignment to .{expected_seq} (Full ID: {base_id or found_base}.{expected_seq})", 
                        "redirect_text": actual_redirect, 
                        "severity": "low"
                    })
                
                # Check 3: Content Missing
                # Strip ID from combined text and check remaining
                content_part = combined[combined.find(raw_id_text) + len(raw_id_text):].strip()
                content_part = re.sub(r'^[:.\s]+', '', content_part)
                
                if not is_meaningful_content(content_part):
                    all_errors.append({
                        "pos": position,
                        "where": where_ref, 
                        "what": f"Test scenario content is missing. Found ID '{found_id}'.", 
                        "suggestion": f"Add description after ID {found_id}", 
                        "redirect_text": actual_redirect, 
                        "severity": "high"
                    })

        # Sort errors scenario-wise (by position) then by severity
        severity_map = {"high": 0, "medium": 1, "low": 2}
        all_errors.sort(key=lambda x: (x.get("pos", 0), severity_map.get(x.get("severity", "low"), 2)))
        
        # Remove the pos key before outputting to keep it clean if desired, 
        # or keep it if it's useful. I'll remove it for the final output.
        for err in all_errors:
            if 'pos' in err: del err['pos']

        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(all_errors, f, indent=4)
            
        print(json.dumps(all_errors, indent=4))
        sys.exit(1 if all_errors else 0)

    except Exception as e:
        print(json.dumps([{"where": "9. Expected Results for Pass:", "what": f"Error: {str(e)}", "severity": "high"}]))
        sys.exit(1)

if __name__ == "__main__":
    main()
