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

        # 1. Get Base ID with robust fallbacks
        base_id = None
        
        # Check Frontpage Data first as a strong source
        fp_content = data.get('frontpage_data', {}).get('content', [])
        for item in fp_content:
            m = re.search(r'\b(\d+\.\d+\.\d+)\b', str(item))
            if m:
                base_id = m.group(1)
                break
        
        if not base_id:
            for sec in sections:
                title = sec.get('title', '').strip().lower()
                # Check Sections 1, 2, or 8.1
                is_relevant = ('security' in title and 'requirement' in title) or \
                              ('itsar' in title and 'section' in title) or \
                              ('number' in title and 'scenarios' in title) or \
                              re.search(r'^(1|2|8\.1)\.', title)
                
                if is_relevant:
                    # Check specialized fields
                    relevant_fields = ['security_requirement', 'itsar_section_details', 'content']
                    for field in relevant_fields:
                        val = sec.get(field, '')
                        if isinstance(val, list):
                            for item in val:
                                text = item.get('text', '') if isinstance(item, dict) else str(item)
                                m = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                                if m: base_id = m.group(1); break
                        else:
                            m = re.search(r'\b(\d+\.\d+\.\d+)\b', str(val))
                            if m: base_id = m.group(1); break
                        if base_id: break
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
                ms = test_id_pattern.findall(text)
                if len(ms) > 1:
                    parts = re.split(r'(?=Test\s+Sc[eh]n?ario|TC\s*[:.-]|T\.C\.\s*|\d+\.\d+\.\d+\.\d+|Verify\s+|Test\s+Case\s+)', text, flags=re.IGNORECASE)
                    for p in parts:
                        if is_meaningful_content(p): fragments.append(p.strip())
                elif text.strip(): fragments.append(text.strip())

            pos = 0
            for frag in fragments:
                pos += 1
                exp_id = f"{base_id}.{pos}" if base_id else str(pos)
                ids = test_id_pattern.findall(frag)
                
                # ID Reference for reporting (Always use Expected ID for 'where')
                ref_label = f"Test Scenario {exp_id}"
                where_ref = f"{expected9_title} - {ref_label}"

                if not ids:
                    all_errors.append({
                        "where": where_ref, 
                        "what": f"ID missing in content. in {ref_label}", 
                        "suggestion": f"Expected: 'Test Scenario {exp_id}:'", 
                        "redirect_text": redirect_title, 
                        "severity": "medium"
                    })
                    continue
                
                tid = ids[0]
                
                # Check 1: Sequence/Alignment/Base ID
                if tid != exp_id:
                    if base_id and ".".join(tid.split(".")[:3]) != base_id:
                        all_errors.append({
                            "where": where_ref, 
                            "what": f"Base ID mismatch: Found '{tid}'. in {ref_label}", 
                            "suggestion": f"Expected Base ID: {base_id}", 
                            "redirect_text": redirect_title, 
                            "severity": "low"
                        })
                    else:
                        all_errors.append({
                            "where": where_ref, 
                            "what": f"ID alignment mismatch: Found '{tid}'. in {ref_label}", 
                            "suggestion": f"Correct ID to {exp_id}", 
                            "redirect_text": redirect_title, 
                            "severity": "low"
                        })
                
                # Check 2: Content Missing
                id_pos = frag.find(tid)
                suffix = frag[id_pos + len(tid):].strip()
                if not is_meaningful_content(suffix):
                    all_errors.append({
                        "where": where_ref, 
                        "what": f"test scenario content missing. in {ref_label}", 
                        "suggestion": f"Add description after ID {tid}", 
                        "redirect_text": redirect_title, 
                        "severity": "high"
                    })

        all_errors.sort(key=lambda x: {"high":0, "medium":1, "low":2}.get(x.get("severity", "low"), 2))
        
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
