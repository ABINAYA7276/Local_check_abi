import json
import os
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
        try:
            with open('output.json', 'w', encoding='utf-8') as f_out:
                json.dump(data, f_out, indent=4)
        except Exception as write_err:
             # If we can't write to file, we still print to stdout
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
        # We need to find the section first.
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Loose check to FIND the section
            if title.startswith('1.') or 'itsar' in title_lower or section.get('section_id') == 'SEC-01':
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

        # STRICT TITLE VALIDATION (BLOCKING)
        found_title = target_section.get('title', '').strip()
        # It MUST start with "1." and contain "ITSAR" AND "Section No & Name" (case-insensitive)
        # This rejects incomplete titles like "1. ITSAR"
        title_lower = found_title.lower()
        if not (found_title.startswith("1.") and "itsar" in title_lower and "section no & name" in title_lower):
             all_errors.append({
                "where": found_title if found_title else "Section 1",
                "what": "Section 1 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "severity": "High"
            })
             # BLOCKING - Return immediately
             output_result(all_errors, 0)

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
                "where": found_title,
                "what": f"content missing. Found: '{found_text_sample}'",
                "suggestion": "Provide the ITSAR section number and name details.",
                "redirect_text": stable_redirect,
                "severity": "High"
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
