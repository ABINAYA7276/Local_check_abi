import json
import os
import re
import sys
import argparse

def is_valid_sentence(text):
    """
    Check if text looks like a proper sentence.
    A valid sentence should:
    - Have at least 2 words
    """
    if not text or not isinstance(text, str):
        return False
    
    text = text.strip()
    if not text:
        return False
    
    # Remove quotes from beginning/end
    text = text.strip("'\"")
    
    # Basic check for at least 2 words
    words = text.split()
    if len(words) < 2:
        return False
    
    return True

def main():
    def output_result(data, exit_code=0):
        # Sort by severity: Title issues (Low/Medium) before Content issues (High)
        severity_priority = {"Low": 0, "Medium": 1, "High": 2}
        if isinstance(data, list):
            data.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium'), 1))
        
        try:
            with open('output.json', 'w', encoding='utf-8') as f_out:
                json.dump(data, f_out, indent=4)
        except Exception:
             pass
        print(json.dumps(data, indent=4))
        sys.exit(exit_code)

    parser = argparse.ArgumentParser(description="Validate Section 1: ITSAR Section No & Name.")
    parser.add_argument("json_file", type=str, help="Path to the structured JSON file")
    
    args = parser.parse_args()
    file_path = args.json_file

    if not os.path.isfile(file_path):
        output_result([{
            "where": "Section 1 - ITSAR Section No & Name",
            "what": f"File not found: {file_path}",
            "suggestion": "Provide a valid JSON file path"
        }], 1)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        
        # Search for Section 1 strictly
        # It must start with '1.' or have explicit ID 'SEC-01' (if available), 
        # but User emphasized "check only section 1... or else overlap".
        # So we filter strictly.
        
        # 1. IDENTIFICATION & TITLE CHECK (BLOCKING)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            # Identify by keywords
            if 'itsar' in title_lower and 'section' in title_lower and 'name' in title_lower:
                target_section = section
                break
        
        # Standard definitions for reporting
        standard_title = "1. ITSAR Section No & Name"
        stable_redirect = "ITSAR Section No & Name"
        
        all_errors = []

        if not target_section:
             all_errors.append({
                "where": "Section 1",
                "what": "Section 1 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            })
             output_result(all_errors, 0)

        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body (Strict validation)
        has_correct_body = "itsar section no & name" in title_lower

        # Identify any leading number prefix (handles 1., 1.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("1.")

        # 1. Number Checks
        if not has_correct_num:
            if has_any_number:
                wrong_num = num_prefix_match.group(1).strip()
                all_errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '1.'",
                    "suggestion": f"Replace section number '{wrong_num}' with '1.'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            else:
                all_errors.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })

        # 2. Body / Formatting Checks (Spacing)
        # Relaxed identification
        has_itsar_body = "itsar" in title_lower and "section" in title_lower and "name" in title_lower
        
        if has_itsar_body:
            # Check for any missing spaces or general incorrect formatting
            if not has_correct_body:
                all_errors.append({
                    "where": standard_title,
                    "what": f"Incorrect formatting or missing space in the title. Found: '{found_title}'",
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
        else:
            # Title is entirely wrong or absent
            return output_result([{
                "where": standard_title,
                "what": "Section 1 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "High"
            }], 0)

        # 2. CONTENT VALIDATION (Only reached if Title is valid)
        has_valid_content = False
        found_text_sample = ""
        
        def is_valid_content(t):
            t_clean = str(t).strip()
            if not t_clean: return False
            # Reject only specific placeholders
            if t_clean.lower() in ['none', 'n/a', 'nil', '.', '-', '_', '...', '']:
                return False
            # Accept any other content, even single letters
            return True

        # Check all possible content fields
        content_sources = []
        # Check fields and aggregate content
        if 'itsar_section_details' in target_section:
            details = target_section['itsar_section_details']
            if isinstance(details, list):
                content_sources.append(" ".join([str(i) for i in details if i]))
            else:
                content_sources.append(str(details))
            
        if 'content' in target_section:
            content = target_section['content']
            if isinstance(content, list):
                content_sources.append(" ".join([str(i) for i in content if i]))
            else:
                content_sources.append(str(content))

        for item in content_sources:
            text = ""
            if isinstance(item, str): text = item
            elif isinstance(item, dict): text = item.get('text', '') or item.get('section_detail', '')
            
            if is_valid_content(text):
                has_valid_content = True
                found_text_sample = text
                break
            elif text and not found_text_sample:
                 found_text_sample = text
        
        if not has_valid_content:
            all_errors.append({
                "where": standard_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the ITSAR section number and name details.",
                "redirect_text": found_title,
                "severity": "High"
            })

        # 3. ITSAR SECTION NUMBER FORMAT CHECK
        # Rules:
        #   - If section number is a plain integer like "1" (no dots) → error, severity: Low
        #   - If no section number is found at all → error, severity: Low
        if 'itsar_section_details' in target_section:
            details = target_section['itsar_section_details']
            raw_details = details if isinstance(details, list) else [str(details)]
            for detail_item in raw_details:
                detail_str = str(detail_item).strip()
                # Extract section number: handles patterns like 'Section 1:' or '1.1:' etc.
                sec_num_match = re.search(r'(?:Section\s+)?(\d+(?:\.\d+)*)', detail_str, re.IGNORECASE)
                if sec_num_match:
                    sec_num = sec_num_match.group(1)
                    # Valid ITSAR section number must contain at least one dot (e.g., 1.1, 1.1.2)
                    if '.' not in sec_num:
                        all_errors.append({
                            "where": standard_title,
                            "what": (
                                f"ITSAR section number '{sec_num}' is invalid. "
                                f"A plain integer is not allowed; section number must include sub-sections "
                                f"(e.g., '1.1', '1.1.2')."
                            ),
                            "suggestion": (
                                f"Replace plain section number '{sec_num}' with a valid dotted section number "
                                f"(e.g., '1.1', '1.1.2')."
                            ),
                            "redirect_text": found_title,
                            "severity": "Low"
                        })
                else:
                    # No section number found at all in this detail entry
                    if detail_str:  # Only flag if there is actual text (not empty)
                        all_errors.append({
                            "where": standard_title,
                            "what": (
                                f"ITSAR section number is missing in detail: '{detail_str}'. "
                                f"Expected a dotted section number (e.g., '1.1', '1.1.2')."
                            ),
                            "suggestion": "Add the ITSAR section number in dotted format (e.g., 'Section 1.1: Name').",
                            "redirect_text": found_title,
                            "severity": "Low"
                        })

        output_result(all_errors, 0)

    except json.JSONDecodeError:
        output_result([{
            "where": "Section 1 - ITSAR Section No & Name",
            "what": "Failed to decode JSON",
            "suggestion": "Ensure the JSON file is valid"
        }], 1)
    except Exception as e:
        output_result([{
            "where": "Section 1 - ITSAR Section No & Name",
            "what": f"Error: {str(e)}",
            "suggestion": "Check the file path and JSON structure"
        }], 1)

if __name__ == "__main__":
    main()
