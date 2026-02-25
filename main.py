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
        test_id_pattern = re.compile(r'\b(\d+\.\d+\.\d+\.\d+)\b')

        # Get Base ID
        base_id = None
        for sec in sections:
            t = sec.get('title', '').strip().lower()
            if '2' in t and 'security' in t and 'requirement' in t:
                val = str(sec.get('security_requirement', ''))
                m = re.search(r'\b(\d+\.\d+\.\d+)\b', val)
                if m: base_id = m.group(1); break
                for c in sec.get('content', []):
                    ct = c.get('text', '') if isinstance(c, dict) else str(c)
                    m = re.search(r'\b(\d+\.\d+\.\d+)\b', ct)
                    if m: base_id = m.group(1); break
            if base_id: break

        # Find Section 9
        target_section = None
        for sec in sections:
            t = sec.get('title', '').strip().lower()
            if '9' in t and 'expected' in t and 'results' in t and 'pass' in t:
                if re.search(r'^9\.\d+', t): continue
                target_section = sec
                break

        expected9_title = "9. Expected Results for Pass:"
        redirect_title = "Expected Results for Pass"
        all_errors = []

        if not target_section:
            all_errors.append({"where": expected9_title, "what": "Section 9 missing", "suggestion": f"Add {expected9_title}", "severity": "high"})
        else:

            
            # Process scenarios
            raw = []
            er = target_section.get('expected_results', [])
            if er:
                for x in er: raw.append(x.get('expected_result', '') if isinstance(x, dict) else str(x))
            else:
                for x in target_section.get('content', []): raw.append(x.get('text', '') if isinstance(x, dict) else str(x))
            
            fragments = []
            for text in raw:
                # Clean the text: remove newlines and tabs to prevent terminal issues
                clean_text = " ".join(text.split()).strip()
                ms = test_id_pattern.findall(clean_text)
                if len(ms) > 1:
                    parts = re.split(r'(?=Test\s+Sc[eh]n?ario|TC\s*[:.-]|T\.C\.\s*|\d+\.\d+\.\d+\.\d+|Verify\s+|Test\s+Case\s+)', clean_text, flags=re.IGNORECASE)
                    for p in parts:
                        p_clean = p.strip()
                        if is_meaningful_content(p_clean): fragments.append(p_clean)
                else:
                    # Preserve the entry even if empty to maintain positional alignment (Scenario 1, 2, 3...)
                    fragments.append(clean_text)

            pos = 0
            for frag in fragments:
                pos += 1
                exp_id = f"{base_id}.{pos}" if base_id else str(pos)
                ids = test_id_pattern.findall(frag)
                if not is_meaningful_content(frag):
                    all_errors.append({
                        "where": f"{expected9_title} - Scenario {pos}", 
                        "what": "content missing. Found empty scenario entry.", 
                        "suggestion": f"Expected: 'Test Scenario {exp_id}: [Add expected result description here]'", 
                        "redirect_text": redirect_title, 
                        "severity": "high"
                    })
                    continue

                if not ids:
                    # Check if "Test Scenario" prefix exists even if ID is missing
                    prefix_pats = [r'Test\s+Sc[eh]n?ario', r'TC\s*[:.-]', r'T\.C\.', r'Test\s+Case']
                    has_prefix = any(re.search(p, frag, re.IGNORECASE) for p in prefix_pats)
                    
                    where_scenario = f"Scenario {pos}"
                    if not has_prefix:
                        # BOTH ARE MISSING
                        all_errors.append({
                            "where": f"{expected9_title} - {where_scenario}", 
                            "what": "Test scenario label and ID are missing", 
                            "suggestion": f"Expected: 'Test Scenario {exp_id}:'", 
                            "redirect_text": redirect_title, 
                            "severity": "high"
                        })
                    else:
                        # ONLY ID IS MISSING
                        all_errors.append({
                            "where": f"{expected9_title} - {where_scenario}", 
                            "what": "Test Scenario ID missing.", 
                            "suggestion": f"Expected: 'Test Scenario {exp_id}:'", 
                            "redirect_text": redirect_title, 
                            "severity": "medium"
                        })
                    continue
                
                tid = ids[0]
                where_ref = f"{expected9_title} - Scenario {pos}"
                ref = f"Test Scenario {tid}"
                
                id_pos = frag.find(tid)
                prefix = frag[:id_pos].strip()
                clean_p = re.sub(r'[:.\-\s]+$', '', prefix)
                pats = [r'Test\s+Sc[eh]n?ario$', r'testcase\s+number$', r'testcase\s+scenario$', r'testcase\s+id$', r'test\s+case\s+number$', r'test\s+case\s+scenario$', r'test\s+case\s+id$', r'\bTC$', r'\bT\.C\.$']
                
                if not any(re.search(p, clean_p, re.IGNORECASE) for p in pats):
                    # Found context logic preserved
                    found_start = frag[:id_pos + len(tid) + 1].strip()
                    is_miss = not clean_p or not any(c.isalnum() for c in clean_p)
                    
                    if is_miss:
                        what_msg = "Incorrect format: 'Test Scenario' Label missing."
                    else:
                        what_msg = f"Incorrect format: 'Test Scenario' Label is incorrect (Found '{clean_p}')."

                    all_errors.append({
                        "where": where_ref, 
                        "what": what_msg, 
                        "suggestion": f"Expected: 'Test Scenario {exp_id}:'", 
                        "redirect_text": redirect_title, 
                        "severity": "medium"
                    })
                
                if tid != exp_id:
                    if base_id and ".".join(tid.split(".")[:3]) != base_id:
                        all_errors.append({"where": where_ref, "what": f"Base ID mismatch: Found '{tid}'. in {ref}", "suggestion": f"Expected Base ID: {base_id}", "redirect_text": redirect_title, "severity": "low"})
                    else:
                        all_errors.append({"where": where_ref, "what": f"ID alignment mismatch: Found '{tid}'. in {ref}", "suggestion": f"Correct ID to {exp_id}", "redirect_text": redirect_title, "severity": "low"})
                
                suffix = frag[id_pos + len(tid):].strip()
                if not is_meaningful_content(suffix):
                    # User requested 'Found' context even for content
                    what_msg = f"test scenario content missing: Found '{suffix}'. in {ref}" if suffix else f"test scenario content missing. in {ref}"
                    all_errors.append({
                        "where": where_ref, 
                        "what": what_msg, 
                        "suggestion": f"Add description after 'Test Scenario {tid}:'", 
                        "redirect_text": redirect_title, 
                        "severity": "high"
                    })

        # Sort logic: Group by Scenario (from 'where' field) then by Severity
        def sort_key(x):
            where = x.get("where", "")
            # Extract scenario number for sorting (e.g. "Scenario 5" -> 5)
            match = re.search(r'Scenario\s+(\d+)', where)
            pos_num = int(match.group(1)) if match else 999
            
            sev_map = {"high": 0, "medium": 1, "low": 2}
            sev_val = sev_map.get(x.get("severity", "low"), 2)
            return (pos_num, sev_val)

        all_errors.sort(key=sort_key)
        
        # Save to output.json as requested
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(all_errors, f, indent=4)
            
        print(json.dumps(all_errors, indent=4))
        sys.exit(1 if all_errors else 0)

    except Exception as e:
        print(json.dumps([{"where": "9. Expected Results for Pass:", "what": f"Error: {str(e)}", "severity": "high"}]))
        sys.exit(1)

if __name__ == "__main__":
    main()
