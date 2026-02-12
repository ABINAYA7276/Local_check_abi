import sys
import io
from pathlib import Path
import os
import argparse
import re
import json
from typing import List, Dict, Tuple, Optional

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
    all_valid = True
    all_errors_table = []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        test_id_pattern = re.compile(r'\b(\d+\.\d+\.\d+\.\d+)\b')

        # 1. Get base ID
        base_id = None
        for section in sections:
            title = section.get('title', '')
            match = re.search(r'^(\d+\.\d+\.\d+):', title)
            if match:
                base_id = match.group(1)
                break
            if re.search(r'2\.\s+Security Requirement', title, re.IGNORECASE) or section.get('section_id') == 'SEC-02':
                content = section.get('content', [])
                for item in content:
                    text = item.get('text', '').strip() if isinstance(item, dict) else str(item).strip()
                    if text:
                        match = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                        if match:
                            base_id = match.group(1)
                            break
                if base_id: break

        # 2. Check for Section 8.4
        section84_found = False
        section84_has_content = False
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            sec_id = section.get('section_id', '')

            # HARD GUARD: Exclude all other known sections
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11']:
                continue

            # Strict Logic for 8.4
            is_section_8_4 = False
            
            # Match SEC-12 (standard for 8.4)
            if sec_id == 'SEC-12':
                is_section_8_4 = True
            
            # Match title '8.4' AND 'Test Execution'
            # This PREVENTS matching "8.4. Test Bed Diam" (which lacks "Execution")
            elif title.startswith('8.4') and 'execution' in title_lower:
                is_section_8_4 = True

            # Handle typo '84.' if it also has 'execution'
            elif title.startswith('84.') and 'execution' in title_lower:
                is_section_8_4 = True
            
            if is_section_8_4:
                section84_found = True
                section84_id = sec_id if sec_id else 'Unknown'
                expected84_title = "8.4. Test Execution Steps"
                
                # Create clean redirect title (Remove leading numbers like 8.4., keep spaces)
                redirect_title = re.sub(r'^[\d\.]+\s*', '', title).strip()

                # Title Validation
                if title.replace(':', '').strip().lower() != expected84_title.replace(':', '').strip().lower():
                    all_valid = False
                    all_errors_table.append({
                        'where': expected84_title,
                        'what': f"Incorrect title: Found '{title}'",
                        'suggestion': f"Change title to exactly '{expected84_title}'",
                        'redirect_text': f"{title}"
                    })
                
                # Handle both 'content' (unstructured) and 'execution_steps' (structured)
                text_sources = []
                
                # Check for structured execution steps first
                if 'execution_steps' in section:
                    for item in section['execution_steps']:
                        if isinstance(item, dict):
                            # The 'test_scenario' field usually contains the ID and description
                            text_sources.append(item.get('test_scenario', '').strip())
                
                # Fallback or additional content
                if 'content' in section:
                    for item in section['content']:
                        if isinstance(item, dict) and item.get('type') == 'paragraph':
                            text_sources.append(item.get('text', '').strip())
                        elif isinstance(item, str):
                            text_sources.append(item.strip())

                position = 0
                
                # Dictionary to track errors per scenario to allow consolidation
                # Key: scen_id, Value: dict with 'header_missing', 'step_errors', 'header_info'
                scenario_tracker = {}

                for text in text_sources:
                    if not text: continue
                    section84_has_content = True
                    
                    matches = test_id_pattern.findall(text)
                    for test_id in matches:
                        position += 1
                        if not base_id:
                            parts = test_id.split('.')
                            if len(parts) == 4:
                                base_id = '.'.join(parts[:3])
                        
                        expected_id = f"{base_id}.{position}" if base_id else test_id
                        
                        # Initialize tracker for this ID
                        if test_id not in scenario_tracker:
                            scenario_tracker[test_id] = {'header_error': None, 'step_error': None, 'expected_id': expected_id}

                        id_pos = text.find(test_id)
                        
                        if id_pos >= 0:
                            prefix_start = max(0, id_pos - 50)
                            prefix_text = text[prefix_start:id_pos].strip()
                            acceptable_patterns = [
                                r'Test\s+Sc[eh]n?ario\s*$', r'testcase\s+number\s*$', 
                                r'testcase\s+scenario\s*$', r'testcase\s+id\s*$', 
                                r'test\s+case\s+number\s*$', r'test\s+case\s+scenario\s*$', 
                                r'test\s+case\s+id\s*$', r'\bTC\s*$', r'\bT\.C\.\s*$'
                            ]
                            is_format_acceptable = any(re.search(pattern, prefix_text, re.IGNORECASE) for pattern in acceptable_patterns)
                            
                            if not is_format_acceptable:
                                all_valid = False
                                all_errors_table.append({
                                    'where': f"Test Scenario {expected_id}:",
                                    'what': f"Incorrect format before ID ({test_id})",
                                    'suggestion': f"Expected: 'Test Scenario {expected_id}:'",
                                    'redirect_text': redirect_title
                                })
                            else:
                                if test_id != expected_id:
                                    if ".".join(test_id.split(".")[:3]) != base_id:
                                        all_valid = False
                                        all_errors_table.append({
                                            'where': f"Test Scenario {expected_id}:",
                                            'what': f"Base ID mismatch ({test_id})",
                                            'suggestion': f"Expected Base ID: {base_id}",
                                            'redirect_text': redirect_title
                                        })
                                    else:
                                        all_valid = False
                                        all_errors_table.append({
                                            'where': f"Test Scenario {expected_id}:",
                                            'what': f"Test Scenario ID out of sequence ({test_id})",
                                            'suggestion': f"Renumber to {expected_id}",
                                            'redirect_text': redirect_title
                                        })
                            
                            suffix = text[id_pos + len(test_id):].strip()
                            # Check if meaningful content exists after the ID and colon
                            # Remove leading colon, dash, space, DOT
                            suffix_clean = re.sub(r'^[:\-\s\.]+', '', suffix)
                            if not suffix_clean:
                                # Mark header error but don't append yet
                                scenario_tracker[test_id]['header_error'] = {
                                    'where': f"Test Scenario {expected_id}:",
                                    'what': "Description missing",
                                    'suggestion': f"Add description after 'Test Scenario {test_id}:'",
                                    'redirect_text': redirect_title
                                }
                
                if not section84_has_content or position == 0:
                    all_valid = False
                    # Only report if we haven't reported title error preventing content find
                    if section.get('title') == expected84_title: 
                         all_errors_table.append({
                            'where': expected84_title,
                            'what': f"missing content. in {expected84_title}",
                            'suggestion': "Ensure Section 8.4 contains test scenarios.",
                            'redirect_text': redirect_title
                        })

                # Check 4: Validate individual Execution Steps content
                if 'execution_steps' in section:
                    for scenario in section['execution_steps']:
                        scenario_text = scenario.get('test_scenario', '').strip()
                        # Extract ID for reporting
                        scen_id_match = test_id_pattern.search(scenario_text)
                        if scen_id_match:
                            scen_id = scen_id_match.group(1)
                            
                            # Ensure tracker exists (it should from previous loop)
                            if scen_id not in scenario_tracker:
                                 scenario_tracker[scen_id] = {'header_error': None, 'step_error': None, 'expected_id': scen_id}
                            
                            steps = scenario.get('steps', [])
                            if not steps:
                                    scenario_tracker[scen_id]['step_error'] = {
                                    'where': f"Test Scenario {scen_id}",
                                    'what': f"No execution steps found for Test Scenario {scen_id}",
                                    'suggestion': "Add execution steps.",
                                    'redirect_text': redirect_title
                                }
                            else:
                                empty_step_indices = []
                                for idx, step_item in enumerate(steps):
                                    step_content = step_item.get('step', '').strip()
                                    clean_step = re.sub(r'^[:\-\s\.]+', '', step_content)
                                    if not step_content or not clean_step:
                                        empty_step_indices.append(str(idx + 1))
                                
                                if empty_step_indices:
                                    steps_str = ", ".join(empty_step_indices)
                                    # Check if ALL steps are missing
                                    steps_fully_missing = (len(empty_step_indices) == len(steps))
                                    
                                    scenario_tracker[scen_id]['step_error'] = {
                                        'where': f"Test Scenario {scen_id}",
                                        'what': f"Missing content in execution steps: {steps_str}",
                                        'suggestion': "Provide valid step descriptions for these steps.",
                                        'redirect_text': redirect_title,
                                        'fully_missing': steps_fully_missing
                                    }
                
                # FINAL PASS: Consolidate Errors
                for test_id, errors in scenario_tracker.items():
                    header_err = errors.get('header_error')
                    step_err = errors.get('step_error')
                    
                    if header_err and step_err:
                        # Both missing? Check if steps are FULLY missing
                        # If steps are fully missing AND header is missing -> "Start to End content missing"
                        steps_fully_missing = step_err.get('fully_missing', False)
                        # If step error was "No execution steps found", treat as fully missing
                        if "No execution steps" in step_err['what']:
                            steps_fully_missing = True
                            
                        if steps_fully_missing:
                            # CONSOLIDATE
                            all_valid = False
                            all_errors_table.append({
                                'where': f"Test Scenario {test_id}:",
                                'what': "Test Scenario content missing fully (Description and all steps)",
                                'suggestion': f"Add description and execution steps for {test_id}",
                                'redirect_text': redirect_title
                            })
                        else:
                            # Header missing + Partial steps missing -> Report both separate
                            all_valid = False
                            all_errors_table.append(header_err)
                            all_errors_table.append(step_err)
                            
                    elif header_err:
                        all_valid = False
                        all_errors_table.append(header_err)
                    elif step_err:
                        all_valid = False
                        all_errors_table.append(step_err)
                
                break
        
        if not section84_found:
             all_valid = False
             all_errors_table.append({
                'where': "8.4. Test Execution Steps",
                'what': "missing section. in 8.4. Test Execution Steps",
                'suggestion': "Section 8.4 is completely missing from the document."
            })
            
    except Exception as e:
        all_errors_table.append({
            'where': "Section 8.4 Processing",
            'what': f"Validation Error: {str(e)}",
            'suggestion': "Check JSON format",
            'redirect_text': "Error"
        })
        all_valid = False

    findings = []
    if all_errors_table:
        for error in all_errors_table:
            findings.append({
                "where": error['where'],
                "what": error['what'],
                "suggestion": error['suggestion'],
                "redirect_text": error.get('redirect_text', '')
            })

    if findings:
        print(json.dumps(findings, indent=4))
    
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(findings, f, indent=4)
    
    if all_valid:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
