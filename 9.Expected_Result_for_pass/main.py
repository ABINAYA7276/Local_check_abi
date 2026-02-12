import sys
import io
from pathlib import Path
import os
import argparse
import re
import json
from typing import List, Dict, Tuple, Optional

def main():
    parser = argparse.ArgumentParser(description="Validate Section 9: Expected Results for Pass.")
    parser.add_argument("json_file", type=str, help="Path to the structured JSON file")
    
    args = parser.parse_args()
    json_file = Path(args.json_file)
    
    if not json_file.is_file():
        print(f"Error: Path is not a file - {json_file}")
        sys.exit(1)

    # Force utf-8 encoding for stdout/stderr
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
        
        # Pattern to match test case IDs like 1.1.3.1
        test_id_pattern = re.compile(r'\b(\d+\.\d+\.\d+\.\d+)\b')

        # 1. Get base ID from Section 3 (SEC-03) or Section 2
        base_id = None
        for section in sections:
            title = section.get('title', '')
            section_id = section.get('section_id', '')
            
            # Try Section 3 title match (e.g., "1.1.7: ...")
            match = re.search(r'^(\d+\.\d+\.\d+):', title)
            if match:
                base_id = match.group(1)
                break
                
            # Try Section 2 content match
            if re.search(r'2\.\s+Security Requirement', title, re.IGNORECASE) or section_id == 'SEC-02':
                content = section.get('content', [])
                for item in content:
                    text = ""
                    if isinstance(item, dict):
                        text = item.get('text', '').strip()
                    elif isinstance(item, str):
                        text = item.strip()
                    
                    if text:
                        match = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
                        if match:
                            base_id = match.group(1)
                            break
                if base_id: break

        # 2. Check for Section 9: Expected Results for Pass
        section9_found = False
        section9_has_content = False
        
        section_id = 'Unknown'

        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            sec_id = section.get('section_id', '')

            # HARD GUARD: Exclude all other known sections
            if sec_id in ['SEC-01', 'SEC-02', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-07', 'SEC-08', 'SEC-09', 'SEC-10', 'SEC-11', 'SEC-12']:
                continue

            # Strict Logic for Section 9
            is_section_9 = False
            
            # Match SEC-13 (standard for 9)
            if sec_id == 'SEC-13':
                is_section_9 = True
            
            # Match title '9.' AND 'Expected'
            elif title.startswith('9.') and 'expected' in title_lower:
                is_section_9 = True
            
            # EXPLICIT OVERLAP PREVENTION for Section 1 masquerading
            if 'itsar' in title_lower:
                is_section_9 = False

            if is_section_9:
                section9_found = True
                section_id = sec_id if sec_id else 'Unknown'
                
                # Title Validation
                expected_main_title = "9. Expected Results for Pass:"
                normalized_title = re.sub(r'\s+', ' ', title)
                if normalized_title.replace(':', '').strip().lower() != expected_main_title.replace(':', '').strip().lower():
                    all_valid = False
                    all_errors_table.append({
                        'where': expected_main_title,
                        'what': f"Incorrect title: Found '{title}'",
                        'suggestion': f"Change title to exactly '{expected_main_title}'",
                        'redirect_text': f"{title}"
                    })
                
                expected_results = section.get('expected_results', [])
                
                # Fallback to content if structure missing
                text_sources = []
                if expected_results:
                     for item in expected_results:
                         text_sources.append(item.get('expected_result', '').strip())
                elif 'content' in section:
                     for item in section['content']:
                         if isinstance(item, dict):
                             text_sources.append(item.get('text', '').strip())
                
                if text_sources:
                    section9_has_content = True
                    position = 0
                    
                    for text in text_sources:
                        if not text: continue
                        
                        matches = test_id_pattern.findall(text)
                        for test_id in matches:
                            position += 1
                            if not base_id:
                                parts = test_id.split('.')
                                if len(parts) >= 3:
                                    base_id = '.'.join(parts[:3])
                            
                            expected_id = f"{base_id}.{position}" if base_id else test_id
                            id_pos = text.find(test_id)
                            
                            if id_pos >= 0:
                                # Check Prefix Format
                                prefix_start = max(0, id_pos - 50)
                                prefix_text = text[prefix_start:id_pos].strip()
                                
                                acceptable_patterns = [
                                    r'Test\s+Sc[eh]n?ario\s*[:.-]?\s*$', r'test\s+case\s*[:.-]?\s*$', 
                                    r'TC\s*[:.-]?\s*$', r'\bT\.C\.\s*[:.-]?\s*$'
                                ]
                                
                                is_format_acceptable = any(re.search(p, prefix_text, re.IGNORECASE) for p in acceptable_patterns)
                                
                                if not is_format_acceptable:
                                    all_valid = False
                                    all_errors_table.append({
                                        'where': f"Test Scenario {expected_id}",
                                        'what': f"Incorrect format before ID ({test_id})",
                                        'suggestion': f"Expected: 'Test Scenario {expected_id}:'",
                                        'redirect_text': f"{title}"
                                    })

                                # Check ID Sequence
                                if test_id != expected_id:
                                    if ".".join(test_id.split(".")[:3]) != base_id:
                                         all_valid = False
                                         all_errors_table.append({
                                            'where': f"Test Scenario {expected_id}",
                                            'what': f"Base ID mismatch ({test_id})",
                                            'suggestion': f"Expected Base ID: {base_id}",
                                            'redirect_text': f"{title}"
                                        })
                                    else:
                                         all_valid = False
                                         all_errors_table.append({
                                            'where': f"Test Scenario {expected_id}",
                                            'what': f"ID alignment mismatch ({test_id})",
                                            'suggestion': f"Renumber to {expected_id}",
                                            'redirect_text': f"{title}"
                                        })
                                
                                # Check Content Suffix
                                suffix = text[id_pos + len(test_id):].strip()
                                clean_suffix = re.sub(r'^[:.\-\s]+', '', suffix)
                                if not clean_suffix:
                                     all_valid = False
                                     all_errors_table.append({
                                        'where': f"Test Scenario {expected_id}",
                                        'what': "Expected Result content missing",
                                        'suggestion': f"Add result description after '{test_id}:'",
                                        'redirect_text': f"{title}"
                                    })
                break
        
        if not section9_found:
             all_valid = False
             all_errors_table.append({
                'where': "9. Expected Results for Pass:",
                'what': "Section 9 missing",
                'suggestion': "Ensure Section 9 is present.",
                'redirect_text': "9. Expected Results for Pass:"
            })
        elif not section9_has_content:
             # Only report empty if found but truly empty
             all_valid = False
             all_errors_table.append({
                'where': "9. Expected Results for Pass:",
                'what': "Section 9 content missing",
                'suggestion': "Add expected results.",
                'redirect_text': f"{title}"
            })
            
    except Exception as e:
        print(f"[ERROR] Validation failed: {e}")
        all_valid = False

    # Collect findings into a list for JSON output
    findings = []
    if all_errors_table:
        for i, error in enumerate(all_errors_table, 1):
            findings.append({
                "where": error['where'],
                "what": error['what'],
                "suggestion": error['suggestion'],
                "redirect_text": error.get('redirect_text', '')
            })

    # Save to output.json first (silent)
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(findings, f, indent=4)
    except Exception:
        pass

    if findings:
        print(json.dumps(findings, indent=4))
    
    if all_valid:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
