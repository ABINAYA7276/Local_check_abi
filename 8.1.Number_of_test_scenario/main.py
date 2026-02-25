import sys
import io
from pathlib import Path
import os
import argparse
import re
import json
from typing import List, Dict, Tuple, Optional

def is_meaningful_content(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    cleaned = text.strip()
    # Remove common labels GLOBALLY to see if there is actual content
    temp = re.sub(r'(Positive|Negative)\s+Sc[eh]n?ario\s*[:.-]*', '', cleaned, flags=re.IGNORECASE).strip()
    temp = re.sub(r'(HTTPS|SSH|SNMP|Note|Via)\s*[:.-]*', '', temp, flags=re.IGNORECASE).strip()
    
    if not temp or temp.lower() in [".", ":", "-", "_", "...", "n/a", "none", "nil"]:
        return False
    if not re.search(r'\w', temp):
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="Validate Section 8.1: Number of Test Scenarios.")
    parser.add_argument("json_file", type=str, help="Path to the structured JSON file")
    args = parser.parse_args()
    json_path = args.json_file

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        test_id_pattern = re.compile(r'\b(\d+\.\d+\.\d+\.\d+)\b')
        
        # 1. Get base ID (from Section 2)
        base_id = None
        for section in sections:
            sec_id = section.get('section_id', '')
            title = section.get('title', '').strip()
            if sec_id == 'SEC-02' or re.search(r'Security\s+Requirement', title, re.IGNORECASE) or re.search(r'^2\.', title):
                # Check directly in section fields
                for key, val in section.items():
                    if key in ['section_id', 'level']: continue
                    text = str(val)
                    m = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                    if m:
                        base_id = m.group(1)
                        break
                # Check in content list
                if not base_id:
                    for item in section.get('content', []):
                        text = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                        m = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                        if m:
                            base_id = m.group(1)
                            break
                if base_id: break

        # Fallback: Check frontpage_data if not found in Section 2/3
        if not base_id:
            fp_data = data.get('frontpage_data', {})
            fp_content = fp_data.get('content', [])
            for text in fp_content:
                m = re.search(r'\b(\d+\.\d+\.\d+)\b', str(text))
                if m:
                    base_id = m.group(1)
                    break

        all_errors = []
        all_valid = True
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            if re.search(r'8\.1|Number\s+of\s+Test\s+Scenarios', title, re.IGNORECASE):
                redirect_val = re.sub(r'^\d+\.\d?\.\s*', '', title).strip() or "Number of Test Scenarios:"
                expected_title = "8.1. Number of Test Scenarios:"
                
                # Title Validation
                if title.replace(':', '').strip().lower() != expected_title.replace(':', '').strip().lower():
                    all_errors.append({
                        "where": expected_title,
                        "what": f"Incorrect Title: '{title}'.",
                        "suggestion": f"Expected: '{expected_title}'",
                        "severity": "medium",
                        "pos": 0
                    })
                    # We don't break anymore, continue to check content if possible

                # Process Content Fragments
                content_items = section.get('content', [])
                all_fragments = []
                current_frag = ""
                
                start_markers = [r'Test\s+Sc[eh]n?ario', r'TC\s*[:.-]', r'T\.C\.', r'Test\s+Case']
                
                for item in content_items:
                    text = item.get('text', '') if isinstance(item, dict) else str(item)
                    clean_text = " ".join(text.split()).strip()
                    if not clean_text: continue
                    
                    matches = test_id_pattern.findall(clean_text)
                    
                    if len(matches) > 1:
                        if current_frag:
                            all_fragments.append(current_frag)
                            current_frag = ""
                        marker_regex = r'(?=Test\s+Sc[eh]n?ario|TC\s*[:.-]|T\.C\.\s*|\d+\.\d+\.\d+\.\d+|Verify\s+|Test\s+Case\s+)'
                        parts = re.split(marker_regex, clean_text, flags=re.IGNORECASE)
                        for p in parts:
                            if p.strip(): all_fragments.append(p.strip())
                        continue

                    is_sub_point = re.match(r'^(Positive|Negative)\s+Sc[eh]n?ario', clean_text, re.IGNORECASE) or \
                                   re.match(r'^(HTTPS|SSH|SNMP|Note|Via):?$', clean_text, re.IGNORECASE)
                    
                    has_id = len(matches) == 1
                    has_label = any(re.search(m, clean_text, re.IGNORECASE) for m in start_markers)
                    is_broken_header = re.fullmatch(r'[:\.\-\s]+', clean_text)
                    
                    is_start = has_id or has_label or is_broken_header
                    
                    if not is_start and current_frag:
                        if not is_sub_point and not current_frag.strip().endswith(':'):
                            is_start = True
                    
                    if is_start:
                        if current_frag: all_fragments.append(current_frag)
                        current_frag = clean_text
                    else:
                        if current_frag: current_frag += " " + clean_text
                        else: current_frag = clean_text
                if current_frag:
                    all_fragments.append(current_frag)
                
                if not base_id:
                    all_errors.append({
                        "where": expected_title,
                        "what": "Base ID wrong / missing: Could not find valid ID (e.g., 1.1.3) in Section 2 or Front Page.",
                        "suggestion": "Update Section 2 with the correct Security Requirement ID",
                        "severity": "high", "pos": 0
                    })

                expected_num = 1
                for frag in all_fragments:
                    matches = test_id_pattern.findall(frag)
                    found_id = matches[0] if matches else None
                    
                    has_label = any(re.search(p, frag, re.IGNORECASE) for p in start_markers)
                    
                    if not (found_id or has_label):
                        continue
                        
                    expected_id = f"{base_id}.{expected_num}" if base_id else f"X.X.X.{expected_num}"
                    block_where = f"8.1. Number of Test Scenarios: - Test Scenario {expected_id}"
                    
                    header_content = ""
                    if found_id:
                        found_at = frag.find(found_id)
                        header_content = frag[found_at + len(found_id):].strip()
                    else:
                        header_content = frag
                    header_content = re.sub(r'^[:\-\s]+', '', header_content).strip()

                    id_missing = not found_id
                    
                    # New detailed content check for sub-scenarios
                    missing_subparts = []
                    has_sub_headers = False
                    
                    sub_patterns = [
                        (r'Positive\s+Sc[eh]n?ario', "Positive Scenario"),
                        (r'Negative\s+Sc[eh]n?ario', "Negative Scenario")
                    ]
                    
                    # Split into pieces if sub-headers exist
                    marker_regex = r'(' + '|'.join(p[0] for p in sub_patterns) + r')'
                    parts = re.split(marker_regex, header_content, flags=re.IGNORECASE)
                    
                    if len(parts) > 1:
                        has_sub_headers = True
                        # parts = [text_before, header1, remaining1, header2, remaining2...]
                        for i in range(1, len(parts), 2):
                            label_found = parts[i]
                            # Find which human-friendly name this matches
                            h_name = "Positive Scenario" if "positive" in label_found.lower() else "Negative Scenario"
                            content_after = parts[i+1] if i+1 < len(parts) else ""
                            if not is_meaningful_content(content_after):
                                missing_subparts.append(h_name)
                    
                    description_missing = False
                    if has_sub_headers:
                        if missing_subparts:
                            description_missing = True
                    else:
                        description_missing = not is_meaningful_content(header_content)
                    
                    label_missing = False
                    if found_id:
                        id_pos = frag.find(found_id)
                        prefix = frag[:id_pos].strip()
                        label_missing = not any(re.search(p, prefix, re.IGNORECASE) for p in start_markers)
                    else:
                        label_missing = not any(re.search(p, frag, re.IGNORECASE) for p in start_markers)

                    display_id = found_id if found_id else expected_id
                    block_where = f"8.1. Number of Test Scenarios: - Test Scenario {expected_id}"
                    
                    if id_missing or label_missing or description_missing:
                        what_parts = []
                        if label_missing: what_parts.append("label")
                        if id_missing: what_parts.append("ID")
                        
                        if description_missing:
                            if missing_subparts:
                                what_parts.append(f"{' and '.join(missing_subparts)} missing content")
                            else:
                                what_parts.append("description")
                        
                        if len(what_parts) == 1:
                            comp = what_parts[0]
                            if "missing content" in comp:
                                what_msg = f"In Test Scenario {display_id}, {comp}."
                            else:
                                what_msg = f"In Test Scenario {display_id}, {comp} is missing."
                        else:
                            has_content_string = any("missing content" in p for p in what_parts)
                            combined = ", ".join(what_parts[:-1]) + " and " + what_parts[-1]
                            if has_content_string:
                                what_msg = f"In Test Scenario {display_id}, {combined}."
                            else:
                                what_msg = f"In Test Scenario {display_id}, {combined} are missing."

                        suggestion = f"Expected: 'Test Scenario {expected_id}: [Description]'"
                        
                        all_errors.append({
                            "where": block_where,
                            "what": what_msg,
                            "suggestion": suggestion,
                            "redirect_text": redirect_val,
                            "severity": "high" if (id_missing or description_missing) else "medium",
                            "pos": expected_num
                        })
                        
                        # Also report sequence mismatch if it's not missing but just wrong
                        if found_id and found_id != expected_id:
                             all_errors.append({
                                "where": block_where,
                                "what": f"Incorrect sequence order: Found '{found_id}' instead of '{expected_id}'.",
                                "suggestion": suggestion,
                                "redirect_text": redirect_val,
                                "severity": "low", "pos": expected_num + 0.1
                            })
                        
                        expected_num += 1
                    elif found_id != expected_id:
                        is_base_mismatch = False
                        if base_id and found_id:
                            found_parts = found_id.split('.')
                            if len(found_parts) >= 3:
                                found_prefix = ".".join(found_parts[:3])
                                if found_prefix != base_id:
                                    is_base_mismatch = True
                        
                        if is_base_mismatch:
                            what_msg = f"Base ID wrong: Found '{found_id}'."
                            suggestion = f"Expected prefix: '{base_id}'"
                            expected_num += 1
                        else:
                            # Strict +1 skip logic
                            is_skip = False
                            try:
                                fnd_num = int(found_id.split('.')[-1])
                                if fnd_num == expected_num + 1:
                                    is_skip = True
                            except:
                                pass

                            if is_skip:
                                # They skipped one (expected_num) and we found the next (expected_num + 1)
                                what_msg = f"In Test Scenario {expected_id}, label, ID and description are missing. (Found '{found_id}' instead)."
                                expected_num += 2 # Consume both position slots
                            else:
                                what_msg = f"Incorrect sequence order: Found '{found_id}' instead of '{expected_id}'."
                                expected_num += 1
                            
                            suggestion = f"Expected: 'Test Scenario {expected_id}: [Description]'"

                        all_errors.append({
                            "where": block_where,
                            "what": what_msg,
                            "suggestion": suggestion,
                            "redirect_text": redirect_val,
                            "severity": "low", "pos": expected_num - 1
                        })
                    else:
                        # Perfect match
                        expected_num += 1
                
                if expected_num == 1:
                    all_errors.append({
                        "where": expected_title,
                        "what": "Content missing (No test scenarios found).",
                        "suggestion": "Ensure scenarios follow the 'Test Scenario [ID]: Description' format.",
                        "redirect_text": redirect_val,
                        "severity": "high", "pos": 0
                    })
                break
        
        if not any(re.search(r'8\.1|Number\s+of\s+Test\s+Scenarios', s.get('title', ''), re.IGNORECASE) for s in sections):
             all_errors.append({
                'where': "8.1. Number of Test Scenarios:",
                'what': "Section 8.1 missing",
                'suggestion': "Add 8.1. Number of Test Scenarios:",
                'severity': "high", "pos": 0
            })

        # Final Sort and Print
        all_errors.sort(key=lambda x: (x.get('pos', 999), {"high":0, "medium":1, "low":2}.get(x.get('severity', 'low'), 3)))
        
        # Clean Output
        final_findings = []
        import string
        printable = set(string.printable)

        def safe_str(s):
            # Aggressive sanitization: keep only standard printable characters, remove CRLF
            s = str(s).replace('\r', ' ').replace('\n', ' ')
            clean = "".join(filter(lambda x: x in printable and x not in '\r\n', s))
            return " ".join(clean.split()).strip()

        for e in all_errors:
            res = {
                "where": safe_str(e.get('where', '')),
                "what": safe_str(e.get('what', '')),
                "suggestion": safe_str(e.get('suggestion', '')),
                "severity": e.get('severity', 'low'),
            }
            if 'redirect_text' in e: 
                res["redirect_text"] = safe_str(e['redirect_text'])
            final_findings.append(res)

        print(json.dumps(final_findings, indent=4))
        
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(final_findings, f, indent=4)
        
        if final_findings: sys.exit(1)
        else: sys.exit(0)

    except Exception as e:
        err_res = [{"where": "Error", "what": str(e), "suggestion": "Fix JSON", "severity": "high"}]
        print(json.dumps(err_res, indent=4))
        sys.exit(1)

if __name__ == "__main__":
    main()
