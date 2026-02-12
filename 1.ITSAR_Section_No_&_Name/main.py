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
    parser = argparse.ArgumentParser(description="Validate Section 1: ITSAR Section No & Name.")
    parser.add_argument("json_file", type=str, help="Path to the structured JSON file")
    
    args = parser.parse_args()
    file_path = args.json_file

    if not os.path.isfile(file_path):
        print(json.dumps([{
            "where": "Section 1 - ITSAR Section No & Name",
            "what": f"File not found: {file_path}",
            "suggestion": "Provide a valid JSON file path"
        }], indent=4))
        sys.exit(1)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        
        # Search for Section 1 strictly
        # It must start with '1.' or have explicit ID 'SEC-01' (if available), 
        # but User emphasized "check only section 1... or else overlap".
        # So we filter strictly.
        
        for section in sections:
            title = section.get('title', '').strip()
            # Strict check: Starts with "1." AND NOT "1.1", "11.", etc.
            # AND excludes other known sections if they accidentally match "1." (unlikely but safe)
            if title.startswith('1.') and not title.startswith('1.1'):
                target_section = section
                break
            
            # Also allow explicit ID if available
            if section.get('section_id') == 'SEC-01':
                target_section = section
                break
        
        all_errors = []

        if not target_section:
            all_errors.append({
                "where": "Section 1 - ITSAR Section No & Name",
                "what": "missing section. in Section 1 - ITSAR Section No & Name",
                "suggestion": "Add Section 1 (ITSAR Section No & Name) to the document",
                "redirect_text": "Sections > Missing Section 1"
            })
        else:
            section_id = target_section.get('section_id', 'Unknown')
            actual_title = target_section.get('title', '').strip()
            # Normalize title for comparison (remove trailing colon if present)
            clean_title = actual_title.rstrip(':').strip()
            
            expected_title = "1. ITSAR Section No & Name"
            
            if clean_title != expected_title:
                all_errors.append({
                    "where": "Section 1 - ITSAR Section No & Name",
                    "what": f"Incorrect title: Found '{actual_title}'",
                    "suggestion": f"Change title to exactly '{expected_title}'",
                    "redirect_text": f"{actual_title}"
                })

            has_valid_content = False
            items_checked = []
            
            # Check content in 'itsar_section_details' or 'content'
            # Priority to 'itsar_section_details' if structured extraction worked
            
            content_sources = []
            if 'itsar_section_details' in target_section:
                details = target_section['itsar_section_details']
                if isinstance(details, list):
                    content_sources.extend(details)
            
            if 'content' in target_section:
                content = target_section['content']
                if isinstance(content, list):
                     content_sources.extend(content)

            for item in content_sources:
                text = ""
                if isinstance(item, str):
                    text = item
                elif isinstance(item, dict):
                    text = item.get('text', '') or item.get('section_detail', '')
                
                text = text.strip()
                if not text: continue
                
                # Ignore placeholders
                if text.lower() in ['none', 'n/a', 'nil', '.', '-', '_', '...']:
                    continue
                
                items_checked.append(text)
                
                if is_valid_sentence(text):
                    has_valid_content = True
                    break
            
            if not has_valid_content:
                if items_checked:
                    # Found content but it was invalid (too short)
                    invalid_text = items_checked[0]
                    short_text = (invalid_text[:50] + '...') if len(invalid_text) > 50 else invalid_text
                    all_errors.append({
                        "where": "Section 1 - ITSAR Section No & Name",
                        "what": f"Content not valid (too brief). Found: '{short_text}'",
                        "suggestion": "Replace with complete descriptive sentence for ITSAR Section No & Name",
                        "redirect_text": f"{actual_title}"
                    })
                else:
                    # No content found at all
                    all_errors.append({
                        "where": "Section 1 - ITSAR Section No & Name",
                        "what": f"Content missing: Add a description of the ITSAR Section in {actual_title}",
                        "suggestion": "Add section content details",
                        "redirect_text": f"{actual_title}"
                    })

        if all_errors:
            print(json.dumps(all_errors, indent=4))
            with open('output.json', 'w', encoding='utf-8') as f:
                json.dump(all_errors, f, indent=4)
            sys.exit(1)
        else:
            # If valid, print empty list or nothing? User prompt implies checking output.
            # "returns a list of errors or None" in user code. 
            # I will print [] if valid to be explicit.
            print("[]")
            with open('output.json', 'w', encoding='utf-8') as f:
                json.dump([], f, indent=4)
            sys.exit(0)

    except json.JSONDecodeError:
        print(json.dumps([{
            "where": "Section 1 - ITSAR Section No & Name",
            "what": "Failed to decode JSON",
            "suggestion": "Ensure the JSON file is valid"
        }], indent=4))
        sys.exit(1)
    except Exception as e:
        print(json.dumps([{
            "where": "Section 1 - ITSAR Section No & Name",
            "what": f"Error: {str(e)}",
            "suggestion": "Check the file path and JSON structure"
        }], indent=4))
        sys.exit(1)

if __name__ == "__main__":
    main()
