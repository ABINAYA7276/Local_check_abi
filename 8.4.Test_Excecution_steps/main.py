import sys
import io
import pathlib
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

def normalize_text(text: str) -> str:
    if not text: return ""
    text = text.lower().strip()
    
    # 1. Semantic Normalization: Standardize common terms
    text = re.sub(r'\b(verified|verifying|verification|to\s*verify)\b', 'verify', text)
    text = re.sub(r'\b(supports|supported|supporting)\b', 'support', text)
    text = re.sub(r'\b(mechanism|mechanisms)\b', 'mechanism', text)
    text = re.sub(r'\b(requirement|requirements)\b', 'requirement', text)
    text = re.sub(r'\b(protocol|protocols)\b', 'protocol', text)
    text = re.sub(r'\b(security|secure|secured)\b', 'secure', text)
    
    # 2. General Cleanup
    # Remove common prefixes
    text = re.sub(r'^test\s*scenario\s*[\d\.\s]+[:\-]*\s*', '', text)
    text = re.sub(r'^test\s*case\s*name\s*[:\-]*\s*', '', text)
    
    # Remove all non-alphanumeric except spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Collapse whitespace
    text = " ".join(text.split())
    return text

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
        test_id_pattern = re.compile(r'(\d+[\d\.\s]*\d+)') # Pattern for scenario IDs

        # 1. Get base ID (from requirements)
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

        # 2. Section 8.4 Configuration
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

        # Handle title prefix reporting
        num_match = re.match(r'^([\d\.]+)', found_title)
        actual_prefix = num_match.group(1).strip() if num_match else "8.4"
        display_title = f"{actual_prefix} {standard_title.split(' ', 1)[1]}"

        # Title Checks
        has_any_number = num_match is not None
        if found_title != standard_title:
            error_details = []
            has_correct_num = found_title.startswith("8.4.")
            if has_any_number and not has_correct_num:
                error_details.append(f"Wrong section number (Found: '{actual_prefix}', Expected: '8.4.')")
            elif not has_any_number:
                error_details.append(f"Section number missing (Found: '{found_title}')")
            
            if "test execution steps" not in found_title.lower():
                is_space_issue = any(part in found_title.lower() for part in ["executionsteps", "testexecution"])
                if is_space_issue:
                    error_details.append(f"Incorrect formatting - space issue (Found: '{found_title}')")
                else:
                    error_details.append(f"Incorrect formatting (Found: '{found_title}')")
            
            if error_details:
                all_errors_table.append({
                    "where": display_title,
                    "what": "Section title is incorrect. " + " ".join(error_details),
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })

        # Process Scenarios
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

        # base_id is preserved from global detection (lines 66-90)
        scenario_tracker = {}
        first_id_last_part = None
        found_id_count = 0
        for source in text_sources:
            text = source['text']
            if not text: continue
            
            m = test_id_pattern.search(text)
            if not m: continue
            
            found_id_count += 1
            found_id = re.sub(r'[\s]+', '', m.group(1))
            
            if base_id is None:
                parts = found_id.split('.')
                if len(parts) >= 2:
                    base_id = ".".join(parts[:-1])
                    first_id_last_part = parts[-1]
                else:
                    base_id = "" # Fallback
                    first_id_last_part = "1"
            
            # ID Alignment Check
            exp_id = f"{base_id}.{found_id_count}" if base_id else found_id
            where_ref = f"{display_title} - Test Scenario {exp_id}"
            
            title_errors = []
            # 1. Prefix & Space Check
            # Extract text before the ID
            m_all = re.search(r'^(.*?)(?:\d+[\d\.\s]*\d+)', text)
            prefix_text = m_all.group(1).strip() if m_all else ""
            
            if prefix_text:
                if re.fullmatch(r'TestScenario', prefix_text, re.IGNORECASE):
                    title_errors.append("Incorrect format: Found 'TestScenario' (missing space)")
                elif not re.fullmatch(r'Test\s+Scenario', prefix_text, re.IGNORECASE):
                    title_errors.append(f"Garbage text in title: Found '{prefix_text}', Expected: 'Test Scenario'")
            else:
                title_errors.append("Missing prefix 'Test Scenario' before the ID")

            # 2. Sequence Check
            if found_id != exp_id:
                title_errors.append(f"test scenario id wrong. Found '{found_id}'. (Alignment mismatch)")

            if title_errors:
                all_errors_table.append({
                    "where": where_ref,
                    "what": " | ".join(title_errors),
                    "suggestion": f"Expected: {exp_id}",
                    "redirect_text": redirect_label,
                    "severity": "Low"
                })
            
            # 2 & 3. Content and Steps Check
            has_steps = any(is_meaningful_content(s.get('step', '') if isinstance(s, dict) else str(s)) for s in source['steps'])
            
            # (Similarity Check Functions Removed)

            # 3. Content Check
            where_content = f"{where_ref} - Content"
            # Does it have any meaningful steps?
            step_text = " ".join([str(s.get('step', '')) if isinstance(s, dict) else str(s) for s in source['steps']])
            
            if not is_meaningful_content(step_text):
                all_errors_table.append({
                    "where": where_content, 
                    "what": "test scenario content missing.",
                    "suggestion": "Add technical execution steps.",
                    "redirect_text": redirect_label, 
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
        what = error.get('what', '').lower()
        
        # Priority 1: Alignment mismatch (ID wrong)
        type_priority = 0 if "alignment mismatch" in what or "id wrong" in what else 1
        
        if where == display_title: 
            return (-1, [], type_priority, severity_order.get(error.get("severity", "Low"), 2))
        
        match = re.search(r'Test Scenario ([\d\.]+)', where)
        if match:
            id_parts = [int(p) for p in match.group(1).split('.') if p.isdigit()]
            return (0, id_parts, type_priority, severity_order.get(error.get("severity", "Low"), 2))
            
        return (1, [where], type_priority, severity_order.get(error.get("severity", "Low"), 2))

    all_errors_table.sort(key=get_sort_key)
    output_result(all_errors_table)

if __name__ == "__main__":
    main()
