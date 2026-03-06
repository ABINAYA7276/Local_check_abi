import json
import os
import sys
import re

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
        candidates = []
        errors = []
        expected_title = "8.2. Test Bed Diagram"

        for section in sections:
            title = section.get('title', '').strip()
            title_lower = title.lower()
            
            # Match keywords: '8.2', 'test', 'bed', 'diagram'
            if '8.2' in title and 'test' in title_lower and 'bed' in title_lower and 'diagram' in title_lower:
                candidates.append(section)
        
        if not candidates:
            return [{
                "where": expected_title, 
                "what": "Section 8.2 missing", 
                "suggestion": f"Add {expected_title}", 
                "severity": "high"
            }]
        
        primary_section = candidates[0]
        actual_title = primary_section.get('title', '').strip()
        # Clean Redirect Text: Remove leading number, spaces, or colon
        redirect_title = re.sub(r'^\d+\.\d?\.\s*', '', actual_title).strip()
        
        # Title Validation
        norm_actual = actual_title.replace(':', '').strip().lower()
        norm_expected = expected_title.replace(':', '').strip().lower()
        
        if norm_actual != norm_expected:
             return [{
                "where": expected_title,
                "what": "Section 8.2 missing",
                "suggestion": f"Add {expected_title}",
                "severity": "high"
            }]

        # Content Validation
        content = primary_section.get('content', [])
        errors = []
        
        has_image = any(isinstance(item, dict) and item.get('type') == 'image' for item in content)
        
        if not has_image:
            errors.append({
                "where": f"{actual_title}",
                "what": "Test Bed Diagram image is missing.",
                "suggestion": "Add the diagram image in Section 8.2",
                "redirect_text": redirect_title,
                "severity": "high"
            })
        
        figure_caption_pattern = re.compile(r'^[Ff]igure\s+([\d\.]+)\s*([-–: ])\s*(.*)$', re.IGNORECASE)
        
        img_found = False
        for i, item in enumerate(content):
            if isinstance(item, dict) and item.get('type') == 'image':
                img_found = True
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
                        "where": f"{actual_title} - Figure Check",
                        "what": "Figure caption is missing under the diagram.",
                        "suggestion": "Add caption: 'Figure 8.2.1- Test Bed Diagram'",
                        "redirect_text": redirect_title,
                        "severity": "high"
                    })
                else:
                    # Validate the found caption
                    cap_match = figure_caption_pattern.match(caption_text)
                    full_id = cap_match.group(1).strip('.')
                    sep = cap_match.group(2)
                    figure_title = cap_match.group(3).strip()
                    
                    # 1. ID Check
                    if full_id != '8.2.1' and not full_id.startswith('8.2.'):
                        errors.append({
                            "where": f"{actual_title} - Figure ID Check",
                            "what": f"Incorrect Figure ID: Found '{full_id}'.",
                            "suggestion": "Expected: '8.2.1'",
                            "redirect_text": redirect_title,
                            "severity": "medium"
                        })
                    
                    # 2. Name Check - Must be "Test Bed Diagram" only
                    norm_title = " ".join(figure_title.lower().split())
                    if norm_title != "test bed diagram":
                        errors.append({
                            "where": f"{actual_title} - Figure Name Check",
                            "what": f"Incorrect Figure Name: Found '{figure_title}'.",
                            "suggestion": "Expected: 'Test Bed Diagram'",
                            "redirect_text": redirect_title,
                            "severity": "medium"
                        })

        return errors

    except Exception as e:
        return [{"where": "Section 8.2", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_8_2(json_path)
    
    # Sort by severity
    severity_priority = {"high": 0, "medium": 1, "low": 2}
    if isinstance(result, list):
        result.sort(key=lambda x: severity_priority.get(x.get('severity', 'medium'), 1))
        
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
