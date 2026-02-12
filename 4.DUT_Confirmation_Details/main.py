import json
import os
import sys

def check_section_4(file_path):
    """
    Checks Section 4 (DUT Confirmation Details).
    Strictly identifies ONLY Section 4 related blocks to avoid 'collapsing' with other sections.
    """
    if not os.path.exists(file_path):
        return [{"where": "Section 4", "what": "File not found", "suggestion": "Provide valid path"}]

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])
        candidates = []
        expected_title = "4. DUT Confirmation Details"
        
        # 1. Strictly identify Section 4
        
        for section in sections:
            title = section.get('title', '').strip()
            
            # Strict logic: Starts with '4.' AND NOT '4.1' (subsections)
            # OR explicit ID matched
            if title.startswith('4.') and not title.startswith('4.1'):
                 candidates.append(section)
            elif section.get('section_id') == 'SEC-04':
                 candidates.append(section)
        
        if not candidates:
            return [{
                "where": "Section 4 - DUT Confirmation Details",
                "what": "Section 4 missing",
                "suggestion": f"Add {expected_title}",
                "redirect_text": f"{expected_title}"
            }]
        
        # 2. SELECT PRIMARY (For Title Check)
        primary_section = candidates[0]

        errors = []
        actual_title = primary_section.get('title', '').strip()
        
        # Normalize title for comparison
        clean_title = actual_title.rstrip(':').strip()
        
        if clean_title != expected_title:
            errors.append({
                "where": "Section 4 - DUT Confirmation Details",
                "what": f"Incorrect title: Found '{actual_title}'",
                "suggestion": f"Change title to exactly '{expected_title}'",
                "redirect_text": f"{actual_title}"
            })
            
        has_text = False
        # 3. Content Validation
        for target in candidates:
            for field in [target.get('content', []), target.get('itsar_section_details', []), target.get('dut_details', [])]:
                items = field if isinstance(field, list) else ([field] if field else [])
                for item in items:
                    text = ""
                    itype = ""
                    if isinstance(item, dict):
                        text = item.get('text', '').strip()
                        itype = item.get('type', '')
                    elif isinstance(item, str): text = item.strip()
                    
                    if text:
                        tl = text.lower()
                        if "is accessed from the test machine" not in tl and "image" not in tl and not tl.startswith("figure"):
                            has_text = True
                    
                    if isinstance(item, dict) and itype == 'table':
                        headers = item.get('headers', [])
                        rows = item.get('rows', [])
                        # Simple keyword check for relevant table
                        if any(req in " ".join([str(h).lower() for h in headers]) for req in ['interface', 'port']):
                            has_text = True
                            expected_headers = ["Interfaces", "No.of Ports", "Interface Type", "Interface Name"]
                            for h_idx, exp in enumerate(expected_headers):
                                if h_idx < len(headers):
                                    h = str(headers[h_idx])
                                    h_norm = h.lower().replace(' ', '').replace('.', '').replace('_', '').replace('noof', '')
                                    exp_norm = exp.lower().replace(' ', '').replace('.', '').replace('_', '').replace('noof', '')
                                    
                                    # Very permissive matching
                                    if h_norm != exp_norm and h_norm not in exp_norm and exp_norm not in h_norm:
                                        errors.append({
                                            "where": "Section 4 - DUT Confirmation Details",
                                            "what": f"Incorrect header in table at Column {h_idx+1}: Found '{h}', expected '{exp}'",
                                            "suggestion": f"Rename header to '{exp}'",
                                            "redirect_text": "DUT Interface Status details"
                                        })
                                else:
                                    errors.append({
                                        "where": "Section 4 - DUT Confirmation Details",
                                        "what": f"Missing column {h_idx+1} in table: Expected '{exp}'",
                                        "suggestion": f"Add column '{exp}'",
                                        "redirect_text": "DUT Interface Status details"
                                    })
                            for r_idx, row in enumerate(rows, 1):
                                miss = []
                                for c_idx, cell in enumerate(row):
                                    if not str(cell).strip(): 
                                        col_name = headers[c_idx] if c_idx < len(headers) else f"Col {c_idx+1}"
                                        miss.append(str(col_name))
                                if miss:
                                    errors.append({
                                        "where": "Section 4 - DUT Confirmation Details",
                                        "what": f"Missing value(s) in Row {r_idx}: {', '.join(miss)}",
                                        "suggestion": f"Provide values for: {', '.join(miss)}",
                                        "redirect_text": "DUT Interface Status details"
                                    })
        
        if not has_text and not errors:
            errors.append({
                "where": "Section 4 - DUT Confirmation Details",
                "what": f"Content missing: Add DUT details in {actual_title}",
                "suggestion": "Add DUT details (table with Interfaces, Ports, etc.)",
                "redirect_text": f"{actual_title}"
            })
        return errors
    except Exception as e:
        return [{"where": "Section 4", "what": f"Error: {e}"}]

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'dutjson.json'
    result = check_section_4(json_path)
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4)
    print(json.dumps(result, indent=4))
