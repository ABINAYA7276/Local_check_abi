import sys
import io
from pathlib import Path
import os
import argparse
import re
import json
from typing import List, Dict, Tuple, Optional

def main():
    parser = argparse.ArgumentParser(description="Validate Section 8.1: Number of Test Scenarios.")
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

        # 2. Check for Section 8.1
        # Improved identification to catch typos like "81." or "Scarios"
        section81_found = False
        section81_has_content = False
        
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            sec_id = section.get('section_id', '')

            # Strict Section 8.1 Identification
            # Exclude other known sections to prevent overlap
            if sec_id in ['SEC-08', 'SEC-07', 'SEC-06', 'SEC-05', 'SEC-04', 'SEC-03', 'SEC-02', 'SEC-01', 'SEC-10', 'SEC-11', 'SEC-12']:
                continue

            is_section_8_1 = (
                sec_id == 'SEC-09' or
                (title.startswith('8.1') and not title.startswith('8.1.')) or 
                title.startswith('81.')
            )

            if is_section_8_1:
                section81_found = True
                section81_id = sec_id if sec_id else 'Unknown'
                expected81_title = "8.1. Number of Test Scenarios:"
                
                # Title Validation
                if title != expected81_title:
                    all_valid = False
                    all_errors_table.append({
                        'where': expected81_title,
                        'what': f"Incorrect title: Found '{title}'",
                        'suggestion': f"Change title '{title}' to exactly '{expected81_title}'",
                        'redirect_text': f"{title}"
                    })
                
                content = section.get('content', [])
                position = 0
                
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'paragraph':
                        text = item.get('text', '').strip()
                        if text:
                            section81_has_content = True
                        
                        matches = test_id_pattern.findall(text)
                        for test_id in matches:
                            position += 1
                            if not base_id:
                                parts = test_id.split('.')
                                if len(parts) == 4:
                                    base_id = '.'.join(parts[:3])
                            
                            expected_id = f"{base_id}.{position}" if base_id else test_id
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
                                        'where': f"Test Scenario {test_id}",
                                        'what': f"Incorrect format before ID ({test_id})",
                                        'suggestion': f"Expected: 'Test Scenario {expected_id}:'",
                                        'redirect_text': f"{title}"
                                    })
                                else:
                                    if test_id != expected_id:
                                        if ".".join(test_id.split(".")[:3]) != base_id:
                                            all_valid = False
                                            all_errors_table.append({
                                                'where': f"Test Scenario {test_id}",
                                                'what': f"Base ID mismatch ({test_id})",
                                                'suggestion': f"Expected Base ID: {base_id}",
                                                'redirect_text': f"{title}"
                                            })
                                        else:
                                            all_valid = False
                                            all_errors_table.append({
                                                'where': f"Test Scenario {test_id}",
                                                'what': f"ID alignment mismatch ({test_id})",
                                                'suggestion': f"Correct ID to {expected_id}",
                                                'redirect_text': f"{title}"
                                            })
                                    
                                    suffix = text[id_pos + len(test_id):].strip()
                                    if not suffix or re.fullmatch(r'[:.\s]+', suffix):
                                        all_valid = False
                                        all_errors_table.append({
                                            'where': f"Test Scenario {test_id}",
                                            'what': "test scenario content missing",
                                            'suggestion': f"Add description after 'Test Scenario {test_id}:'",
                                            'redirect_text': f"{title}"
                                        })
                
                if not section81_has_content or position == 0:
                    all_valid = False
                    all_errors_table.append({
                        'where': expected81_title,
                        'what': f"missing content. in {expected81_title}",
                        'suggestion': "Ensure Section 8.1 contains test scenarios.",
                        'redirect_text': f"{title}"
                    })
                break
        
        if not section81_found:
             all_valid = False
             all_errors_table.append({
                'where': "8.1. Number of Test Scenarios:",
                'what': "missing section. in 8.1. Number of Test Scenarios:",
                'suggestion': "Section 8.1 is completely missing from the document."
            })
            
    except Exception as e:
        all_errors_table.append({
            'where': "Section 8.1 Processing",
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
