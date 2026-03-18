"""
Unified Triad Validator
=======================
Validates consistency of test scenario descriptions across:
  - Section 8.1  : Number of Test Scenarios  (field: description)
  - Section 8.4  : Test Execution Steps      (field: steps[order=0].step)
  - Section 11   : Test Execution            (field: a. Test Case Name)

Output: Section by section (8.1 → 8.4 → 11).
        One error per section per position.
        Each error mentions which other sections also have issues at that position.

Usage:
    python main.py <path_to_structured_json>
"""
import sys
import re
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_meaningful_content(text: str) -> bool:
    if not text: return False
    t = text.strip().lower()
    if t in ['none', 'n/a', 'nil', '.', '-', '_', '...'] or len(t) < 3:
        return False
    if all(c in '.-_,;:!? ' for c in t):
        return False
    return True


def normalize_text(text: str) -> str:
    if not text: return ""
    t = text.lower().strip()
    t = re.sub(r'\b(verified|verifying|verification|to\s*verify)\b', 'verify', t)
    t = re.sub(r'\b(supports|supported|supporting)\b', 'support', t)
    t = re.sub(r'\b(mechanism|mechanisms)\b', 'mechanism', t)
    t = re.sub(r'\b(requirement|requirements)\b', 'requirement', t)
    t = re.sub(r'\b(protocol|protocols)\b', 'protocol', t)
    t = re.sub(r'\b(security|secure|secured)\b', 'secure', t)
    t = re.sub(r'^test\s*case\s*name\s*[:\-]*\s*', '', t)
    t = re.sub(r'^test\s*scen?ario\s*[\d\.\s]+[:\-]*\s*', '', t)
    t = re.sub(r'^positive\s*scenario\s*[:\-]*\s*', '', t)
    t = re.sub(r'^negative\s*scenario\s*[:\-]*\s*', '', t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    return " ".join(t.split())


def check_match(src: str, tgt: str, threshold: float = 0.98) -> bool:
    if not src or not tgt: return False
    ns = normalize_text(src)
    nt = normalize_text(tgt)
    keywords = [w for w in ns.split()
                if len(w) > 3 and w not in {'the', 'and', 'with', 'that', 'this', 'for', 'are'}]
    if not keywords: return False
    hits = sum(1 for kw in keywords if kw in nt)
    return (hits / len(keywords)) >= threshold


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_81_scenarios(sections: list) -> list:
    results = []
    for sec in sections:
        t = sec.get('title', '').strip().lower()
        if 'number' in t and 'test' in t and 'scenario' in t:
            for item in sec.get('test_scenarios', []):
                if not isinstance(item, dict): continue
                sc_id = str(item.get('test_scenario', '')).strip()
                desc  = item.get('description', '')
                if isinstance(desc, list): desc = " ".join(str(x) for x in desc if x)
                results.append({'id': sc_id, 'description': str(desc).strip()})
            if results: break
    return results


def extract_84_scenarios(sections: list) -> list:
    results = []
    for sec in sections:
        t = sec.get('title', '').strip().lower()
        if 'execution' in t and 'step' in t:
            for item in sec.get('execution_steps', []):
                if not isinstance(item, dict): continue
                sc_id = str(item.get('test_scenario', '')).strip()
                steps = item.get('steps', [])
                step0_parts = [
                    str(s.get('step', '')) if isinstance(s, dict) else str(s)
                    for s in steps
                    if (s.get('order') == 0 if isinstance(s, dict) else False)
                ]
                step0 = " ".join(step0_parts).strip()
                results.append({'id': sc_id, 'step0': step0})
            if results: break
    return results


def extract_11_test_cases(sections: list) -> list:
    results = []
    for sec in sections:
        t = sec.get('title', '').strip().lower()
        if re.match(r'^11\.', t) and ('test case number' in t or 'testcase' in t):
            content_items = sec.get('itsar_section_details', sec.get('content', []))
            if not isinstance(content_items, list): content_items = [content_items]
            tc_id = sec.get('title', '').strip()
            current_name = ""
            found_a = False
            for it in content_items:
                txt = it.get('text', '').strip() if isinstance(it, dict) else str(it).strip()
                if not txt: continue
                if re.match(r'^a\.\s*', txt, re.IGNORECASE):
                    tmp = re.sub(
                        r'^a\.\s*(Test\s*Case\s*Name|TestCaseName|Test\s*Case\s*Description|Description)\s*[:.\-]*\s*',
                        '', txt, flags=re.IGNORECASE).strip()
                    found_a = True
                    if tmp:
                        current_name = tmp
                        break
                elif found_a and not current_name and len(txt) > 5:
                    current_name = txt
                    break
            results.append({'tc_id': tc_id, 'name': current_name})
    return results


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <json_file>")
        sys.exit(1)

    json_file = Path(sys.argv[1])
    if not json_file.is_file():
        print(json.dumps([{"where": "System", "what": f"File not found: {json_file}", "severity": "High"}]))
        sys.exit(1)

    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    sections = data.get('sections', [])
    errors   = []

    # ------------------------------------------------------------------
    # 1. Extract content from all three sections
    # ------------------------------------------------------------------
    sc81 = extract_81_scenarios(sections)
    sc84 = extract_84_scenarios(sections)
    tc11 = extract_11_test_cases(sections)

    # Structural absence checks
    if not sc81:
        errors.append({
            "where": "8.1. Number of Test Scenarios",
            "what": "Section 8.1 has no test scenarios.",
            "suggestion": "Add test scenarios with description fields.",
            "redirect_text": "Number of Test Scenarios",
            "severity": "High"
        })
    if not sc84:
        errors.append({
            "where": "8.4. Test Execution Steps",
            "what": "Section 8.4 has no execution steps.",
            "suggestion": "Add execution steps (step with order=0 per scenario).",
            "redirect_text": "Test Execution Steps",
            "severity": "High"
        })
    if not tc11:
        errors.append({
            "where": "11. Test Execution",
            "what": "Section 11 has no test cases.",
            "suggestion": "Add test case entries with 'a. Test Case Name' field.",
            "redirect_text": "Test Execution",
            "severity": "High"
        })

    if not sc81 and not sc84 and not tc11:
        print(json.dumps(errors, indent=4))
        sys.exit(1 if errors else 0)

    # ------------------------------------------------------------------
    # 2. Position-by-position Triad Cross Check
    #    One error per SECTION per position.
    #    Each error mentions which other sections also have issues.
    # ------------------------------------------------------------------
    max_len = max(len(sc81), len(sc84), len(tc11))

    # Keep section errors separate so we can output section by section
    errors_81 = []
    errors_84 = []
    errors_11 = []

    for idx in range(max_len):
        position = idx + 1

        d81     = sc81[idx]['description'] if idx < len(sc81) else None
        sc81_id = sc81[idx]['id']          if idx < len(sc81) else f"#{position}"
        d84     = sc84[idx]['step0']       if idx < len(sc84) else None
        sc84_id = sc84[idx]['id']          if idx < len(sc84) else f"#{position}"
        d11     = tc11[idx]['name']        if idx < len(tc11) else None
        tc11_id = tc11[idx]['tc_id']       if idx < len(tc11) else f"#{position}"

        # Determine the issue (if any) for each section at this position
        issue_81 = ""
        issue_84 = ""
        issue_11 = ""

        # Section 8.1
        if idx < len(sc81):
            if not is_meaningful_content(d81 or ''):
                issue_81 = "description is missing"
            elif d84 is not None and is_meaningful_content(d84) and not check_match(d81 or '', d84):
                issue_81 = "content does not match"
            elif d11 is not None and is_meaningful_content(d11) and not check_match(d81 or '', d11):
                issue_81 = "content does not match"

        # Section 8.4
        if idx < len(sc84):
            if not is_meaningful_content(d84 or ''):
                issue_84 = "step 1 content is missing"
            elif d81 is not None and is_meaningful_content(d81) and not check_match(d81, d84 or ''):
                issue_84 = "content does not match"
        if d84 is None and d81 is not None:
            issue_84 = "scenario entry is missing"

        # Section 11
        if idx < len(tc11):
            if not is_meaningful_content(d11 or ''):
                issue_11 = "content is missing"
            elif d81 is not None and is_meaningful_content(d81) and not check_match(d81, d11 or ''):
                issue_11 = "content does not match"
            elif d84 is not None and is_meaningful_content(d84) and d81 is None and not check_match(d84, d11 or ''):
                issue_11 = "content does not match"
        if d11 is None and d81 is not None:
            issue_11 = "scenario entry is missing"

        # Skip this position if no section has any issue
        if not issue_81 and not issue_84 and not issue_11:
            continue

        # Build a consolidated "what" message for each section
        def clean_name(s_id):
            c = str(s_id)
            c = re.sub(r'(?i)test\s*(scenario|case\s*number|case\s*name|case)?', '', c)
            c = re.sub(r'[:\-]', '', c)
            c = c.strip()
            return c if c else s_id

        def build_what(sec_label, scenario_id, issue, tag):
            other_blocks = []
            
            # Use the global variables collected during validation
            if tag != "81" and issue_81: 
                other_blocks.append(f"8.1 test scenario {clean_name(sc81_id)}")
            if tag != "84" and issue_84: 
                other_blocks.append(f"8.4 test scenario {clean_name(sc84_id)}")
            if tag != "11" and issue_11: 
                other_blocks.append(f"11 test case name {clean_name(tc11_id)}")
            
            clean_id = clean_name(scenario_id)
            entity = "test case name" if tag == "11" else "test scenario"
            base_msg = f"Section {sec_label} {entity} {clean_id} {issue}"
            
            if other_blocks:
                others_str = ", ".join(other_blocks)
                return f"{base_msg} with other section {others_str} content"
                
            return base_msg

        # --- Emit one error per section that has an issue, with cross-mention ---
        if issue_81:
            errors_81.append({
                "where":        f"8.1. Number of Test Scenarios - {sc81_id} - Content",
                "what":         build_what("8.1", sc81_id, issue_81, "81"),
                "suggestion":   "Add or correct the test scenario description to match the other sections.",
                "redirect_text": "Number of Test Scenarios",
                "severity":     "High"
            })

        if issue_84:
            errors_84.append({
                "where":        f"8.4. Test Execution Steps - {sc84_id}",
                "what":         build_what("8.4", sc84_id, issue_84, "84"),
                "suggestion":   "Add or correct the execution step (order=0) to match the other sections.",
                "redirect_text": "Test Execution Steps",
                "severity":     "High"
            })

        if issue_11:
            errors_11.append({
                "where":        f"11. Test Execution - {tc11_id} - a. Test Case Name",
                "what":         build_what("11", tc11_id, issue_11, "11"),
                "suggestion":   "Add or correct 'a. Test Case Name' to match the other sections.",
                "redirect_text": tc11_id,
                "severity":     "High"
            })

    # ------------------------------------------------------------------
    # 3. Output — section by section: 8.1 → 8.4 → 11
    # ------------------------------------------------------------------
    result = errors + errors_81 + errors_84 + errors_11

    print(json.dumps(result, indent=4))
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
    except Exception:
        pass

    sys.exit(1 if result else 0)


if __name__ == "__main__":
    main()
