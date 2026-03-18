"""
Unified Triad Validator
=======================
Validates consistency of test scenario descriptions across:
  - Section 8.1  : Number of Test Scenarios  (field: description)
  - Section 8.4  : Test Execution Steps      (field: steps[order=0].step)
  - Section 11   : Test Execution            (field: a. Test Case Name)

Each position (index 0, 1, 2, ...) represents a single test scenario.
At every position, the content from 8.1, 8.4 and 11 must semantically match
each other (98% keyword threshold).

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
    # Semantic normalisation
    t = re.sub(r'\b(verified|verifying|verification|to\s*verify)\b', 'verify', t)
    t = re.sub(r'\b(supports|supported|supporting)\b', 'support', t)
    t = re.sub(r'\b(mechanism|mechanisms)\b', 'mechanism', t)
    t = re.sub(r'\b(requirement|requirements)\b', 'requirement', t)
    t = re.sub(r'\b(protocol|protocols)\b', 'protocol', t)
    t = re.sub(r'\b(security|secure|secured)\b', 'secure', t)
    # Remove common label prefixes
    t = re.sub(r'^test\s*case\s*name\s*[:\-]*\s*', '', t)
    t = re.sub(r'^test\s*scen?ario\s*[\d\.\s]+[:\-]*\s*', '', t)
    t = re.sub(r'^positive\s*scenario\s*[:\-]*\s*', '', t)
    t = re.sub(r'^negative\s*scenario\s*[:\-]*\s*', '', t)
    # Keep only alphanumeric + spaces
    t = re.sub(r'[^a-z0-9\s]', '', t)
    return " ".join(t.split())


def check_match(src: str, tgt: str, threshold: float = 0.98) -> bool:
    """Return True if 'threshold' fraction of significant keywords from src appear in tgt."""
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
    """
    Returns list of dicts: { 'id': str, 'description': str }
    ordered by appearance in Section 8.1.
    """
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
            if results: break   # found the section
    return results


def extract_84_scenarios(sections: list) -> list:
    """
    Returns list of dicts: { 'id': str, 'step0': str }
    ordered by appearance in Section 8.4. Uses step with order==0 as content.
    """
    results = []
    for sec in sections:
        t = sec.get('title', '').strip().lower()
        if 'execution' in t and 'step' in t:
            for item in sec.get('execution_steps', []):
                if not isinstance(item, dict): continue
                sc_id = str(item.get('test_scenario', '')).strip()
                steps = item.get('steps', [])
                # Get the text of the step whose order == 0
                step0_parts = [
                    str(s.get('step', '')) if isinstance(s, dict) else str(s)
                    for s in steps
                    if (s.get('order') == 0 if isinstance(s, dict) else False)
                ]
                step0 = " ".join(step0_parts).strip()
                results.append({'id': sc_id, 'step0': step0})   # empty if steps is []
            if results: break
    return results


def extract_11_test_cases(sections: list) -> list:
    """
    Returns list of dicts: { 'tc_id': str, 'name': str }
    ordered by appearance in Section 11 (a. Test Case Name).
    """
    results = []
    for sec in sections:
        t = sec.get('title', '').strip().lower()
        if re.match(r'^11\.', t) and ('test case number' in t or 'testcase' in t):
            content_items = sec.get('itsar_section_details', sec.get('content', []))
            if not isinstance(content_items, list): content_items = [content_items]
            # Title of this subsection acts as the TC id
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
    sc81 = extract_81_scenarios(sections)   # list of {id, description}
    sc84 = extract_84_scenarios(sections)   # list of {id, step0}
    tc11 = extract_11_test_cases(sections)  # list of {tc_id, name}

    # Report structural absence
    if not sc81:
        errors.append({
            "where":       "8.1. Number of Test Scenarios",
            "what":        "Section 8.1 has no test scenarios.",
            "suggestion":  "Add test scenarios with description fields.",
            "redirect_text": "Number of Test Scenarios",
            "severity":    "High"
        })
    if not sc84:
        errors.append({
            "where":       "8.4. Test Execution Steps",
            "what":        "Section 8.4 has no execution steps.",
            "suggestion":  "Add execution steps per scenario.",
            "redirect_text": "Test Execution Steps",
            "severity":    "High"
        })
    if not tc11:
        errors.append({
            "where":       "11. Test Execution",
            "what":        "Section 11 has no test cases.",
            "suggestion":  "Add test case entries with 'a. Test Case Name' field.",
            "redirect_text": "Test Execution",
            "severity":    "High"
        })

    if not sc81 and not sc84 and not tc11:
        print(json.dumps(errors, indent=4))
        sys.exit(1 if errors else 0)

    # ------------------------------------------------------------------
    # 2. Position-by-position (order 0, 1, 2 …) Triad Cross Check
    # ------------------------------------------------------------------
    max_len = max(len(sc81), len(sc84), len(tc11))

    for idx in range(max_len):
        position  = idx + 1   # human-readable (starts at 1)

        # Fetch content for each section at this position
        d81  = sc81[idx]['description'] if idx < len(sc81) else None
        sc81_id = sc81[idx]['id'] if idx < len(sc81) else f"#{position}"

        d84  = sc84[idx]['step0'] if idx < len(sc84) else None
        sc84_id = sc84[idx]['id'] if idx < len(sc84) else f"#{position}"

        d11  = tc11[idx]['name'] if idx < len(tc11) else None
        tc11_id = tc11[idx]['tc_id'] if idx < len(tc11) else f"#{position}"

        # Helper: instruction-style suggestion
        def ref_label(src_tag):
            return {
                '81': 'Section 8.1 (Scenario Content)',
                '84': 'Section 8.4 (Step 1)',
                '11': 'Section 11 (Test Case Name)',
            }.get(src_tag, 'the other sections')

        # ------ 2a/2b. Check all three sections together ------
        # Only flag mismatch if content is actually present in both sections
        mismatch_84 = (d81 is not None and d84 is not None
                       and is_meaningful_content(d84)
                       and not check_match(d81, d84))
        mismatch_11 = (d81 is not None and d11 is not None
                       and is_meaningful_content(d11)
                       and not check_match(d81, d11))

        if mismatch_84 and mismatch_11:
            # All three sections have conflicting content — show one merged error
            clean_id = sc81_id.strip(':')
            errors.append({
                "where":       f"Sections 8.1, 8.4, 11 - {sc81_id}",
                "what":        f"Triad Mismatch: Test scenario content is inconsistent across Section 8.1, 8.4, and 11 for {clean_id}.",
                "suggestion":  "Ensure the test scenario content is consistent across all three sections.",
                "redirect_text": "Number of Test Scenarios, Test Execution Steps, Test Execution",
                "severity":    "High"
            })
        else:
            # Show individual errors only if one section fails
            if mismatch_84:
                errors.append({
                    "where":       f"8.4. Test Execution Steps - {sc84_id}",
                    "what":        f"Section 8.4 scenario content does not match Section 8.1 for {sc84_id}.",
                    "suggestion":  f"Synchronize with {ref_label('81')} content.",
                    "redirect_text": "Test Execution Steps",
                    "severity":    "High"
                })
            if mismatch_11:
                errors.append({
                    "where":       f"11. Test Execution - {tc11_id} - a. Test Case Name",
                    "what":        f"Section 11 'Test Case Name' does not match Section 8.1 for {tc11_id}.",
                    "suggestion":  f"Synchronize with {ref_label('81')} content.",
                    "redirect_text": tc11_id,
                    "severity":    "High"
                })

        # Missing scenario in 8.4
        if d84 is None and d81 is not None:
            clean_id = sc81_id.strip(':')
            errors.append({
                "where":       f"8.4. Test Execution Steps - Position {position}",
                "what":        f"Section 8.4 missing scenario for {clean_id}.",
                "suggestion":  f"Add execution step consistent with {ref_label('81')} and {ref_label('11')}.",
                "redirect_text": "Test Execution Steps",
                "severity":    "High"
            })

        # Missing test case in 11
        if d11 is None and d81 is not None:
            errors.append({
                "where":       f"11. Test Execution - Position {position} - a. Test Case Name",
                "what":        f"Section 11 missing test case name for {sc81_id}.",
                "suggestion":  f"Add 'a. Test Case Name' consistent with {ref_label('81')} and {ref_label('84')}.",
                "redirect_text": "Test Execution",
                "severity":    "High"
            })

        # ------ 2c. Check 8.4 vs 11 (extra cross-check when 8.1 missing) ------
        if d81 is None and d84 is not None and d11 is not None:
            if not check_match(d84, d11):
                errors.append({
                    "where":       f"11. Test Execution - {tc11_id} - a. Test Case Name",
                    "what":        f"Section 11 'Test Case Name' does not match Section 8.4 for {tc11_id} (Section 8.1 missing).",
                    "suggestion":  f"Synchronize with {ref_label('84')} content.",
                    "redirect_text": tc11_id,
                    "severity":    "High"
                })

        # ------ 2d. Report missing content in any single section ------
        if idx < len(sc81) and not is_meaningful_content(d81 or ''):
            clean_id = sc81_id.strip(':')
            errors.append({
                "where":       f"8.1. Number of Test Scenarios - {sc81_id} - Content",
                "what":        f"Section 8.1 test scenario content is missing for {clean_id}.",
                "suggestion":  f"Add content matching {ref_label('84')} or {ref_label('11')}.",
                "redirect_text": "Number of Test Scenarios",
                "severity":    "High"
            })

        if idx < len(sc84) and not is_meaningful_content(d84 or ''):
            clean_id = sc84_id.strip(':')
            errors.append({
                "where":       f"8.4. Test Execution Steps - {sc84_id}",
                "what":        f"Section 8.4 step 1 content is missing for {clean_id}.",
                "suggestion":  f"Add execution step consistent with {ref_label('81')} and {ref_label('11')}.",
                "redirect_text": "Test Execution Steps",
                "severity":    "High"
            })

        if idx < len(tc11) and not is_meaningful_content(d11 or ''):
            errors.append({
                "where":       f"11. Test Execution - {tc11_id} - a. Test Case Name",
                "what":        f"Section 11 test case name is missing for {tc11_id}.",
                "suggestion":  f"Add 'a. Test Case Name' consistent with {ref_label('81')} and {ref_label('84')}.",
                "redirect_text": tc11_id,
                "severity":    "High"
            })

    # ------------------------------------------------------------------
    # 3. Sort section by section: 8.1 → 8.4 → 11 → Combined
    # ------------------------------------------------------------------
    def section_order(err):
        where = err.get("where", "")
        if   where.startswith("8.1."): sec_rank = 0
        elif where.startswith("8.4."): sec_rank = 1
        elif where.startswith("11."):  sec_rank = 2
        else:                          sec_rank = 3  # Combined errors last
        # Order by position number within each section
        pos_m = re.search(r'(\d+)$', where.split("-")[0].strip())
        pos_rank = int(pos_m.group(1)) if pos_m else 9999
        return (sec_rank, pos_rank)

    result = sorted(errors, key=section_order)

    print(json.dumps(result, indent=4))
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
    except Exception:
        pass

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
