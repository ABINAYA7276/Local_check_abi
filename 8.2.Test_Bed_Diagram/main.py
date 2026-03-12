import json
import os
import re
import sys

def check_section_8_2(file_path):
    """
    Validate Section 8.2 (Test Bed Diagram).
    Checks for presence, correct title, and diagram/figure reference.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 8.2", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        target_section = None
        standard_title = "8.2. Test Bed Diagram"
        stable_redirect = "Test Bed Diagram"

        # 1. IDENTIFICATION (by static title body)
        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Identify by keywords: 'test', 'bed', 'diagram'
            if 'test' in title_lower and 'bed' in title_lower and 'diagram' in title_lower:
                target_section = section
                break
        
        if not target_section:
            return [{
                "where": standard_title, 
                "what": "Section 8.2 missing", 
                "suggestion": f"Expected: '{standard_title}'", 
                "redirect_text": stable_redirect,
                "severity": "High"
            }]
        
        # IDENTIFICATION SUCCESSFUL
        found_title = target_section.get('title', '').strip()
        title_lower = found_title.lower()

        # Detect the title body (Strict validation)
        has_correct_body = 'test bed diagram' in title_lower

        # Identify any leading number prefix (handles 8.2., 8.., etc.)
        num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
        has_any_number = num_prefix_match is not None
        has_correct_num = found_title.startswith("8.2.")
        
        # Derive potential prefix for figure ID checks (e.g. "8.2")
        derived_prefix = "8.2"
        if num_prefix_match:
            raw_prefix = num_prefix_match.group(1).strip().strip('.')
            # Normalize to X.Y if possible
            parts = [p for p in re.split(r'[\s\.]+', raw_prefix) if p]
            if len(parts) >= 2: derived_prefix = ".".join(parts[:2])

        errors = []
        
        # 1. Number Checks
        expected_num = standard_title.split(' ')[0]
        if not has_correct_num:
            if has_any_number:
                wrong_num = num_prefix_match.group(1).strip()
                errors.append({
                    "where": standard_title,
                    "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '{expected_num}'",
                    "suggestion": f"Replace section number '{wrong_num}' with '{expected_num}'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
            else:
                errors.append({
                    "where": standard_title,
                    "what": f"Section number is missing in the title. Found: '{found_title}'",
                    "suggestion": f"Add the section number prefix '{expected_num}'. Expected: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Medium"
                })

        # 2. Body / Formatting Checks (Spacing)
        has_bed_body = 'test' in title_lower and 'bed' in title_lower and 'diagram' in title_lower
        
        if has_bed_body:
            if not has_correct_body:
                errors.append({
                    "where": standard_title,
                    "what": f"Incorrect formatting or missing space in the title. Found: '{found_title}'",
                    "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                    "redirect_text": found_title,
                    "severity": "Low"
                })
        else:
            # Title is entirely wrong or absent
            return [{
                "where": standard_title,
                "what": "Section 8.2 missing",
                "suggestion": f"Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "High"
            }]
             
        # proceed to content check if we have the body
        
        actual_title = found_title
        # Clean Redirect Text: Remove leading number, spaces, or colon
        redirect_val = re.sub(r'^[\d\.]+\s*', '', actual_title).replace(':', '').strip() or stable_redirect
        
        # Content Validation
        content = target_section.get('content', [])
        
        has_image = any(isinstance(item, dict) and item.get('type') == 'image' for item in content)
        if not has_image:
            errors.append({
                "where": standard_title,
                "what": "Test Bed Diagram image is missing.",
                "suggestion": "Add the diagram image in Section 8.2",
                "redirect_text": found_title,
                "severity": "High"
            })
        
        figure_caption_pattern = re.compile(r'^[Ff]igure\s+([\d\.]+)\s*([-–: ])\s*(.*)$', re.IGNORECASE)
        expected_fig_id = f"{derived_prefix}.1"

        for i, item in enumerate(content):
            if isinstance(item, dict) and item.get('type') == 'image':
                # Check for caption following the image
                has_caption = False
                caption_text = ""
                for j in range(i + 1, len(content)):
                    next_item = content[j]
                    text = next_item.get('text', '').strip() if isinstance(next_item, dict) else str(next_item).strip()
                    if not text: continue
                    
                    if figure_caption_pattern.match(text):
                        has_caption = True
                        caption_text = text
                        break
                    else:
                        break # Found something else
                
                if not has_caption:
                    errors.append({
                        "where": f"{standard_title} - Figure Check",
                        "what": "Figure caption is missing under the diagram.",
                        "suggestion": f"Add caption: 'Figure {expected_fig_id}- Test Bed Diagram'",
                        "redirect_text": found_title,
                        "severity": "High"
                    })
                else:
                    # Validate the found caption
                    cap_match = figure_caption_pattern.match(caption_text)
                    full_id = cap_match.group(1).strip('.')
                    figure_title = cap_match.group(3).strip()
                    
                    # 1. ID Check
                    if full_id != expected_fig_id and not full_id.startswith(f"{derived_prefix}."):
                        errors.append({
                            "where": f"{standard_title} - Figure ID Check",
                            "what": f"Incorrect Figure ID: Found '{full_id}'.",
                            "suggestion": f"Expected: '{expected_fig_id}'",
                            "redirect_text": found_title,
                            "severity": "Medium"
                        })
                    
                    # 2. Name Check - Must be "Test Bed Diagram" (case insensitive, allow flexible spacing)
                    norm_title = " ".join(figure_title.lower().split())
                    if norm_title != "test bed diagram":
                        errors.append({
                            "where": f"{standard_title} - Figure Name Check",
                            "what": f"Incorrect Figure Name: Found '{figure_title}'.",
                            "suggestion": "Expected: 'Test Bed Diagram'",
                            "redirect_text": found_title,
                            "severity": "Medium"
                        })

        return errors

    except Exception as e:
        return [{"where": "Section 8.2", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_2(json_path)
    
    # SORTING: Title issues (Low/Medium) before Content issues (High)
    severity_priority = {"Low": 0, "Medium": 1, "High": 2}
    if isinstance(result, list):
        result.sort(key=lambda x: severity_priority.get(x.get('severity', 'Medium').capitalize(), 1))
        
    # Save to output.json (silent)
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result if result else [], f, indent=4)
    except Exception:
        pass

    if result:
        print(json.dumps(result, indent=4))
        sys.exit(1)
    else:
        sys.exit(0)
