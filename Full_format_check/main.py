import json
import os
import re
import sys
import argparse
import difflib
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional, Tuple, Any, Union

# ==========================================
# SHARED UTILITIES
# ==========================================

def is_meaningful_content(text: str) -> bool:
    if not text: return False
    text = str(text).strip().lower()
    if text == 'na': return True
    if text in ['none', 'n/a', 'nil', 'tbd', '.', '-', '_', '...', '', '---'] or len(text) < 3: return False
    # Avoid strings consisting only of punctuation
    if all(c in '.-_,;:!? ' for c in text): return False
    return True

def normalize_redirect_text(text: str) -> str:
    if not text: return ""
    for char in ['/', '\\', '"', '–', '—', '-', ':']:
        text = text.replace(char, ' ')
    text = re.sub(r'\s+', ' ', text)
    # Ensure dots after numbers have spaces if followed by letters
    text = re.sub(r'(\d\.)\s*(?=[A-Za-z])', r'\1 ', text)
    return text.strip()

def split_into_sentences(text):
    """Split text into sentences, handling common abbreviations."""
    if not text: return []
    text = str(text).replace("e.g.", "eg").replace("i.e.", "ie").replace("etc.", "etc")
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences

def normalize_singular(text: str) -> str:
    """Reduce common plural words to singular for plural-insensitive comparison."""
    if not text: return ""
    t = str(text).lower().strip()
    plural_pairs = [
        (r'\bobservations\b',   'observation'),
        (r'\bdescriptions\b',   'description'),
        (r'\bexecutions\b',     'execution'),
        (r'\bsteps\b',          'step'),
        (r'\bnames\b',          'name'),
        (r'\bnumbers\b',        'number'),
        (r'\bdetails\b',        'detail'),
        (r'\bmechanisms\b',     'mechanism'),
        (r'\brequirements\b',   'requirement'),
        (r'\bprotocols\b',      'protocol'),
        (r'\bevidences\b',      'evidence'),
        (r'\bcases\b',          'case'),
        (r'\bscenarios\b',      'scenario'),
        (r'\binterfaces\b',     'interface'),
        (r'\bentities\b',       'entity'),
        (r'\bsections\b',       'section'),
        (r'\bpolicies\b',       'policy'),
        (r'\bconfigurations\b', 'configuration'),
    ]
    for pattern, replacement in plural_pairs:
        t = re.sub(pattern, replacement, t)
    return " ".join(t.split())

def normalize_for_compare(text: str) -> str:
    return normalize_singular(str(text).lower())

def calculate_semantic_similarity(expected_text, actual_text):
    """Calculate semantic similarity using SequenceMatcher (case + plural insensitive)."""
    return difflib.SequenceMatcher(
        None,
        normalize_for_compare(expected_text),
        normalize_for_compare(actual_text)
    ).ratio()

def find_sentence_differences(expected_text, actual_text):
    """Find missing and extra sentences/words between expected and actual text."""
    expected_sentences = split_into_sentences(normalize_for_compare(expected_text))
    actual_sentences   = split_into_sentences(normalize_for_compare(actual_text))

    expected_normalized = [s.strip() for s in expected_sentences]
    actual_normalized   = [s.strip() for s in actual_sentences]

    missing_sentences = []
    incomplete_sentences = []
    matched_actual_indices = set()

    for i, exp_sent in enumerate(expected_normalized):
        found = False
        best_match_ratio = 0
        best_match_actual = ""
        best_match_idx = -1

        for j, act_sent in enumerate(actual_normalized):
            similarity = difflib.SequenceMatcher(None, exp_sent, act_sent).ratio()
            if similarity > best_match_ratio:
                best_match_ratio = similarity
                best_match_actual = act_sent
                best_match_idx = j

            if similarity > 0.95:
                found = True
                matched_actual_indices.add(j)
                break

        if not found:
            if best_match_ratio > 0.80 and best_match_actual in exp_sent:
                missing_part = exp_sent.replace(best_match_actual, "").strip()
                if missing_part:
                    incomplete_sentences.append(f"{expected_sentences[i]} [Missing: '{missing_part}']")
                    if best_match_idx >= 0:
                        matched_actual_indices.add(best_match_idx)
            else:
                missing_sentences.append(expected_sentences[i])

    extra_sentences = []
    for i, act_sent in enumerate(actual_normalized):
        if i in matched_actual_indices:
            continue
        found = False
        for exp_sent in expected_normalized:
            similarity = difflib.SequenceMatcher(None, act_sent, exp_sent).ratio()
            if similarity > 0.95:
                found = True
                break
        if not found:
            extra_sentences.append(actual_sentences[i])

    return {
        "missing_sentences": missing_sentences + incomplete_sentences,
        "extra_sentences": extra_sentences
    }

def find_section_by_title(sections: List[Dict], title_keywords: List[str]) -> Dict:
    """Find a section by semantically matching its title against keywords."""
    for section in sections:
        title = section.get("title", "").lower()
        if all(keyword.lower() in title for keyword in title_keywords):
            return section
    return {}

# ==========================================
# TRIAD EXTRACTION HELPERS
# ==========================================

def extract_81_triad(sections: List[Dict]) -> List[Dict]:
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

def extract_84_triad(sections: List[Dict]) -> List[Dict]:
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

def extract_11_triad(sections: List[Dict]) -> List[Dict]:
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
                if not found_a and re.match(r'^(\d+\.\d+\.\d+\.\d+)', txt):
                    tc_id = txt
                if re.match(r'^a\.\s*', txt, re.IGNORECASE):
                    tmp = re.sub(r'^a\.\s*(Test\s*Case\s*Name|TestCaseName|Test\s*Case\s*Description|Description)\s*[:.\-]*\s*', '', txt, flags=re.I).strip()
                    found_a = True
                    if tmp:
                        current_name = tmp
                        break
                elif found_a and not current_name and len(txt) > 5:
                    current_name = txt
                    break
            results.append({'tc_id': tc_id, 'name': current_name})
    return results

# ==========================================
# TRIAD VALIDATION UTILITIES (8.1, 8.4, 11)
# ==========================================

def normalize_text_triad(text: str) -> str:
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

def normalize_id_triad(id_text: str) -> str:
    """Extract numeric suffix (e.g. 1.1.1.5) from various ID formats."""
    if not id_text: return ""
    t = id_text.strip().lower()
    t = re.sub(r'^(test\s*scenario|testcase|test\s*case|test\s*case\s*number)\s*', '', t, flags=re.I)
    m = re.search(r'(\d+\.\d+\.\d+\.\d+)', t)
    if m: return m.group(1)
    t = re.sub(r'[:\-].*$', '', t)
    return t.strip()

def check_match_triad(src: str, tgt: str, threshold: float = 0.98) -> bool:
    """Return True if 'threshold' fraction of significant keywords from src appear in tgt."""
    if not src or not tgt: return False
    ns = normalize_text_triad(src)
    nt = normalize_text_triad(tgt)
    keywords = [w for w in ns.split()
                if len(w) > 3 and w not in {'the', 'and', 'with', 'that', 'this', 'for', 'are'}]
    if not keywords: return False
    hits = sum(1 for kw in keywords if kw in nt)
    return (hits / len(keywords)) >= threshold

def check_itsar_subsections(itsar_details: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    definitions = {
        'a': {'label': 'a. Test Case Name', 'keywords': ['test case name', 'testcase name', 'name']},
        'b': {'label': 'b. Test Case Description', 'keywords': ['test case description', 'testcase description', 'description']},
        'c': {'label': 'c. Execution Steps', 'keywords': ['execution steps', 'execution step', 'execution']},
        'd': {'label': 'd. Test Observations', 'keywords': ['test observation', 'testobservation', 'observation']},
        'e': {'label': 'e. Evidence Provided', 'keywords': ['evidence provided', 'evidenceprovided', 'evidence']},
    }
    
    found_map = {k: False for k in definitions}
    content_map = {k: False for k in definitions}
    text_accum = {k: "" for k in definitions}
    
    header_pattern = re.compile(r'^([a-e])[\.\)\s]\s*(.*)$', re.IGNORECASE)
    
    current_section = None
    for item in itsar_details:
        text = str(item).strip()
        if not text: continue
        
        match = header_pattern.match(text)
        found_marker = False
        if match:
            key = match.group(1).lower()
            if key in definitions:
                rem_text = match.group(2).strip()
                norm_rem = normalize_singular(rem_text)
                for kw in definitions[key]['keywords']:
                    if normalize_singular(kw) in norm_rem:
                        found_map[key] = True
                        current_section = key
                        found_marker = True
                        actual_rem = re.sub(r'^' + re.escape(kw) + r'[:\-]?\s*', '', rem_text, flags=re.IGNORECASE).strip()
                        if is_meaningful_content(actual_rem):
                            content_map[key] = True
                            text_accum[key] = actual_rem
                        break
        
        if not found_marker and current_section:
            if is_meaningful_content(text):
                is_another = header_pattern.match(text)
                if not is_another:
                    content_map[current_section] = True
                    text_accum[current_section] = (text_accum[current_section] + " " + text).strip()
                
    errors = []
    for key, info in definitions.items():
        label = info['label']
        if not found_map[key]:
            errors.append({'why': f"Missing section: '{label}' section not found", 'suggestion': f"Add '{label}' section", 'label': label, 'severity': 'High'})
        elif not content_map[key]:
            errors.append({'why': f"Missing content: Found empty in '{label}' section", 'suggestion': f"Add content after '{label}'", 'label': label, 'severity': 'High'})
    return errors, text_accum

def check_section_11_figures(items: List, expected_tc_number: str) -> List[Dict]:
    errors = []
    figure_caption_pattern = re.compile(r'^[Ff]igure[:\-–\s]+([\d\.]+)\s*([-–: ])?\s*(.*)$', re.IGNORECASE)
    
    # Pass 1: Link images to mandatory captions
    img_counter = 0
    for i, item in enumerate(items):
        if isinstance(item, dict) and item.get('type') == 'image':
            img_counter += 1
            has_caption = False
            # Search ahead for the next non-empty text item
            for j in range(i + 1, len(items)):
                next_item = items[j]
                next_text = ""
                if isinstance(next_item, dict):
                    next_text = next_item.get('text', '').strip()
                elif isinstance(next_item, str):
                    next_text = next_item.strip()
                
                if not next_text: continue
                
                if figure_caption_pattern.match(next_text):
                    has_caption = True
                break # Found some text, if it's not a caption, it's missing
            
            if not has_caption:
                ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(img_counter, f"{img_counter}th")
                errors.append({
                    'why': f"Caption missing: Found under {expected_tc_number} ({ordinal} image)",
                    'suggestion': f"Expected: 'Figure {expected_tc_number}.X: description' immediately after the image",
                    'severity': 'Medium'
                })

    # Pass 2: Validate the content of found captions
    found_figures = []
    for item in items:
        text = ""
        if isinstance(item, dict):
            text = item.get('text', '').strip()
        elif isinstance(item, str):
            text = item.strip()
        
        if not text: continue
        cap_match = figure_caption_pattern.match(text)
        if cap_match:
            full_id = cap_match.group(1).strip('.')
            parts = full_id.split('.')
            description = cap_match.group(3).strip()
            found_figures.append({
                'full_id': full_id, 
                'suffix': int(parts[-1]) if parts[-1].isdigit() else 0,
                'text': text,
                'description': description
            })
    
    expected_suffix = 1
    for fig in found_figures:
        correct_id = f"{expected_tc_number}.{expected_suffix}"
        if not fig['full_id'].startswith(expected_tc_number):
             errors.append({'why': f"Incorrect Figure ID alignment: Found 'Figure {fig['full_id']}'", 'suggestion': f"Expected Figure {correct_id}", 'severity': 'Low'})
        elif fig['suffix'] != expected_suffix:
            errors.append({'why': f"Incorrect Figure ID sequence: Found '{fig['text']}'", 'suggestion': f"Expected Figure {correct_id}", 'severity': 'Low'})
        
        if not is_meaningful_content(fig['description']):
            errors.append({'why': f"Figure description is missing for: 'Figure {fig['full_id']}'", 'suggestion': f"Add description after '–'", 'severity': 'Medium'})
            
        expected_suffix += 1
    return errors

# ==========================================
# SECTION VALIDATORS
# ==========================================

def check_section_1(sections: List[Dict], expected: Dict) -> List[Dict]:
    target_section = find_section_by_title(sections, ["itsar", "section"])
    standard_title = "1. ITSAR Section No & Name"
    all_errors = []

    if not target_section:
        return [{"where": "Section 1", "what": "Section 1 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]

    found_title = target_section.get('title', '').strip()
    title_lower = found_title.lower()

    # --- TITLE NUMBER CHECK ---
    has_correct_body = "itsar section no & name" in title_lower
    has_itsar_body = "itsar" in title_lower and "section" in title_lower and "name" in title_lower
    num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
    has_any_number = num_prefix_match is not None
    has_correct_num = found_title.startswith("1.")

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

    # --- TITLE BODY FORMATTING CHECK ---
    if has_itsar_body and not has_correct_body:
        all_errors.append({
            "where": standard_title,
            "what": f"Incorrect formatting or missing space in the title. Found: '{found_title}'",
            "suggestion": f"Fix the title to exactly match: '{standard_title}'",
            "redirect_text": found_title,
            "severity": "Low"
        })
    elif not has_itsar_body:
        return [{
            "where": standard_title,
            "what": "Section 1 missing",
            "suggestion": f"Expected: '{standard_title}'",
            "redirect_text": found_title,
            "severity": "High"
        }]

    has_valid_content = False
    found_text_sample = ""
    content_sources = []

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
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get('text', '') or item.get('section_detail', '')

        if is_meaningful_content(text):
            has_valid_content = True
            found_text_sample = text
            break
        elif text and not found_text_sample:
            found_text_sample = text

    if not has_valid_content and found_text_sample.strip():
        all_errors.append({
            "where": standard_title,
            "what": f"content missing. Found: '{found_text_sample}'",
            "suggestion": "Provide the ITSAR section number and name details.",
            "redirect_text": found_title,
            "severity": "High"
        })

    # --- SEMANTIC CONTENT CHECK ---
    if target_section and "itsar_section_details" in expected:
        doc_itsar_details = target_section.get("itsar_section_details", [])
        if not doc_itsar_details and 'content' in target_section:
             doc_itsar_details = [it.get('text', '') if isinstance(it, dict) else str(it) for it in target_section.get('content', [])]
        
        doc_itsar_details = [str(d).strip() for d in doc_itsar_details if str(d).strip()]
        expected_itsar_details = expected["itsar_section_details"]
        if isinstance(expected_itsar_details, list):
            expected_itsar_text = " ".join([str(d).strip() for d in expected_itsar_details if str(d).strip()])
        else:
            expected_itsar_text = str(expected_itsar_details).strip()

        doc_itsar_text = " ".join(doc_itsar_details)

        if is_meaningful_content(doc_itsar_text):
            semantic_score = calculate_semantic_similarity(expected_itsar_text, doc_itsar_text)
            if semantic_score < 0.95:
                all_errors.append({
                    "where": standard_title,
                    "what": f"ITSAR detail wrong: Found '{doc_itsar_text[:80]}'.",
                    "suggestion": f"Expected: '{expected_itsar_text}'",
                    "redirect_text": "ITSAR Section No & Name",
                    "severity": "High"
                })

    if 'itsar_section_details' in target_section:
        details = target_section['itsar_section_details']
        raw_details = details if isinstance(details, list) else [str(details)]
        for detail_item in raw_details:
            detail_str = str(detail_item).strip()
            sec_num_match = re.search(r'(?:Section\s+)?(\d+(?:\.\d+)*)', detail_str, re.IGNORECASE)
            if sec_num_match:
                sec_num = sec_num_match.group(1)
                if '.' not in sec_num:
                    all_errors.append({
                        "where": standard_title,
                        "what": f"ITSAR section number '{sec_num}' is invalid. A plain integer is not allowed; section number must include sub-sections (e.g., '1.1', '1.1.2').",
                        "suggestion": f"Replace plain section number '{sec_num}' with a valid dotted section number (e.g., '1.1', '1.1.2').",
                        "redirect_text": found_title,
                        "severity": "Low"
                    })
            else:
                if detail_str:
                    all_errors.append({
                        "where": standard_title,
                        "what": f"ITSAR section number is missing in detail: '{detail_str}'. Expected a dotted section number (e.g., '1.1', '1.1.2').",
                        "suggestion": "Add the ITSAR section number in dotted format (e.g., 'Section 1.1: Name').",
                        "redirect_text": found_title,
                        "severity": "Low"
                    })

    return all_errors

def check_section_2(sections: List[Dict], expected: Dict) -> List[Dict]:
    target_section = find_section_by_title(sections, ["security", "requirement"])
    standard_title = "2. Security Requirement No & Name"
    stable_redirect = "Security Requirement No & Name"

    if not target_section:
        return [{"where": standard_title, "what": "Section 2 missing", "suggestion": f"Expected: '{standard_title}'", "redirect_text": stable_redirect, "severity": "High"}]

    errors = []
    found_title = target_section.get('title', '').strip()
    title_lower = found_title.lower()

    # --- TITLE NUMBER CHECK ---
    has_correct_body = "security requirement no & name" in title_lower
    has_sec_body = "security" in title_lower and "requirement" in title_lower and "name" in title_lower
    num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
    has_any_number = num_prefix_match is not None
    has_correct_num = found_title.startswith("2.")

    if not has_correct_num:
        if has_any_number:
            wrong_num = num_prefix_match.group(1).strip()
            errors.append({
                "where": standard_title,
                "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '2.'",
                "suggestion": f"Replace section number '{wrong_num}' with '2.'. Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "Low"
            })
        else:
            errors.append({
                "where": standard_title,
                "what": f"Section number is missing in the title. Found: '{found_title}'",
                "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "Medium"
            })

    # --- TITLE BODY FORMATTING CHECK ---
    if has_sec_body and not has_correct_body:
        errors.append({
            "where": standard_title,
            "what": f"Missing space or incorrect formatting in the title. Found: '{found_title}'",
            "suggestion": f"Fix title to exactly match: '{standard_title}'",
            "redirect_text": found_title,
            "severity": "Low"
        })
    elif not has_sec_body:
        return [{
            "where": standard_title,
            "what": "Section 2 missing",
            "suggestion": f"Expected: '{standard_title}'",
            "redirect_text": found_title,
            "severity": "High"
        }]

    has_valid_content = False
    found_text_sample = ""
    content_sources = []
    
    sec_req = target_section.get('security_requirement', '')
    if sec_req: content_sources.append(sec_req)
    content = target_section.get('content', [])
    if isinstance(content, list):
        for c_item in content:
            if isinstance(c_item, dict):
                if c_item.get('type') != 'image':
                    content_sources.append(c_item.get('text', ''))
            else:
                content_sources.append(str(c_item))

    doc_security_req_text = ""
    for text in content_sources:
        if isinstance(text, list): text = " ".join([str(i) for i in text if i])
        text_str = str(text).strip()
        if text_str:
            if not found_text_sample: found_text_sample = text_str
            if is_meaningful_content(text_str):
                has_valid_content = True
                doc_security_req_text = (doc_security_req_text + " " + text_str).strip()

    if not has_valid_content and found_text_sample.strip():
        errors.append({
            "where": standard_title,
            "what": f"content missing. Found: '{found_text_sample}'",
            "suggestion": "Provide the security requirement number and name details.",
            "redirect_text": found_title,
            "severity": "High"
        })

    # --- SEMANTIC CONTENT CHECK ---
    if "security_requirement" in expected:
        exp_req_raw = expected["security_requirement"]
        expected_security_req = " ".join(exp_req_raw) if isinstance(exp_req_raw, list) else str(exp_req_raw)
        
        if is_meaningful_content(doc_security_req_text):
            semantic_score = calculate_semantic_similarity(expected_security_req, doc_security_req_text)
            if semantic_score < 0.95:
                errors.append({
                    "where": standard_title,
                    "what": f"Security requirement wrong: Found '{doc_security_req_text[:80]}'.",
                    "suggestion": f"Expected: '{expected_security_req}'",
                    "redirect_text": "Security Requirement No & Name",
                    "severity": "High"
                })

    return errors

def check_section_3(sections: List[Dict], expected: Dict) -> List[Dict]:
    target_section = find_section_by_title(sections, ["requirement", "description"])
    standard_title = "3. Requirement Description"
    stable_redirect = "Requirement Description"

    if not target_section:
        return [{"where": standard_title, "what": "Section 3 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]

    errors = []
    found_title = target_section.get('title', '').strip()
    title_lower = found_title.lower()

    # --- TITLE NUMBER CHECK ---
    has_correct_body = "requirement description" in title_lower
    has_req_body = "requirement" in title_lower and "description" in title_lower
    num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
    has_any_number = num_prefix_match is not None
    has_correct_num = found_title.startswith("3.")

    if not has_correct_num:
        if has_any_number:
            wrong_num = num_prefix_match.group(1).strip()
            errors.append({
                "where": standard_title,
                "what": f"Wrong section number in the title. Found: '{wrong_num}', Expected: '3.'",
                "suggestion": f"Replace section number '{wrong_num}' with '3.'. Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "Low"
            })
        else:
            errors.append({
                "where": standard_title,
                "what": f"Section number is missing in the title. Found: '{found_title}'",
                "suggestion": f"Add the section number prefix. Expected: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "Medium"
            })

    # --- TITLE BODY FORMATTING CHECK ---
    if has_req_body and not has_correct_body:
        errors.append({
            "where": standard_title,
            "what": f"Missing space in the title. Found: '{found_title}'",
            "suggestion": f"Add space between words. Expected: '{standard_title}'",
            "redirect_text": found_title,
            "severity": "Medium"
        })
    elif not has_req_body:
        return [{
            "where": standard_title,
            "what": "Section 3 missing",
            "suggestion": f"Expected: '{standard_title}'",
            "redirect_text": found_title,
            "severity": "High"
        }]

    has_valid_content = False
    found_text_sample = ""
    req_desc_val = target_section.get('requirement_description', '')
    doc_req_desc_text = " ".join(req_desc_val) if isinstance(req_desc_val, list) else str(req_desc_val)
    
    if not is_meaningful_content(doc_req_desc_text):
        content_list = target_section.get('content', [])
        for item in content_list:
            text = item.get('text', '') if isinstance(item, dict) else str(item)
            if is_meaningful_content(text):
                has_valid_content = True
                doc_req_desc_text = (doc_req_desc_text + " " + text).strip()
                break
            elif text.strip() and not found_text_sample:
                found_text_sample = text.strip()
    else:
        has_valid_content = True

    if not has_valid_content and found_text_sample.strip():
        errors.append({
            "where": standard_title,
            "what": f"content missing. Found: '{found_text_sample}'",
            "suggestion": "Provide the requirement description details.",
            "redirect_text": found_title,
            "severity": "High"
        })

    # --- SEMANTIC CONTENT CHECK ---
    if "requirement_description" in expected:
        exp_desc_raw = expected["requirement_description"]
        expected_req_desc = " ".join(exp_desc_raw) if isinstance(exp_desc_raw, list) else str(exp_desc_raw)

        if is_meaningful_content(doc_req_desc_text):
            semantic_score = calculate_semantic_similarity(expected_req_desc, doc_req_desc_text)
            if semantic_score < 0.95:
                # diff_result = find_sentence_differences(expected_req_desc, doc_req_desc_text)
                errors.append({
                    "where": standard_title,
                    "what": f"Requirement description wrong: Found '{doc_req_desc_text[:80]}...'.",
                    "suggestion": f"Expected: '{expected_req_desc[:60]}...'",
                    "redirect_text": "Requirement Description",
                    "severity": "High"
                })

    return errors

def check_triad_consistency(sections: List[Dict]) -> List[Dict]:
    """Perform neutral 3-way consistency check across Sections 8.1, 8.4, and 11."""
    errors = []
    sc81 = extract_81_triad(sections)
    sc84 = extract_84_triad(sections)
    tc11 = extract_11_triad(sections)

    if not sc81 or not sc84 or not tc11:
        # These missing sections are already caught by individual checks
        return []

    max_len = max(len(sc81), len(sc84), len(tc11))

    for idx in range(max_len):
        position = idx + 1
        d81  = sc81[idx]['description'] if idx < len(sc81) else None
        id81 = sc81[idx]['id'] if idx < len(sc81) else None
        nid81 = normalize_id_triad(id81 or "")

        d84  = sc84[idx]['step0'] if idx < len(sc84) else None
        id84 = sc84[idx]['id'] if idx < len(sc84) else None
        nid84 = normalize_id_triad(id84 or "")

        d11  = tc11[idx]['name'] if idx < len(tc11) else None
        id11 = tc11[idx]['tc_id'] if idx < len(tc11) else None
        nid11 = normalize_id_triad(id11 or "")

        best_id = id81 or id84 or id11 or f"Position {position}"
        label   = normalize_id_triad(best_id)

        # 1. ID Check
        v_id81, v_id84, v_id11 = bool(nid81), bool(nid84), bool(nid11)
        m_id81_84 = (nid81 == nid84) if (v_id81 and v_id84) else True
        m_id84_11 = (nid84 == nid11) if (v_id84 and v_id11) else True
        m_id81_11 = (nid81 == nid11) if (v_id81 and v_id11) else True

        if v_id81 and v_id84 and v_id11:
            if not m_id81_84 and not m_id84_11 and not m_id81_11:
                errors.append({"where": f"Sections 8.1, 8.4, 11 - {best_id}", "what": f"Scenario IDs mismatch: 8.1='{nid81}', 8.4='{nid84}', 11='{nid11}'.", "suggestion": "Standardize ID across all sections.", "severity": "High"})
            elif m_id84_11 and not m_id81_84:
                errors.append({"where": f"8.1. Number of Test Scenarios - {id81}", "what": f"ID '{nid81}' differs from other sections.", "suggestion": f"Change ID to '{nid84}'.", "severity": "High"})
            elif m_id81_11 and not m_id81_84:
                errors.append({"where": f"8.4. Test Execution Steps - {id84}", "what": f"ID '{nid84}' differs from other sections.", "suggestion": f"Change ID to '{nid81}'.", "severity": "High"})
            elif m_id81_84 and not m_id81_11:
                errors.append({"where": f"11. Test Execution - {id11}", "what": f"ID '{nid11}' differs from other sections.", "suggestion": f"Change ID to '{nid81}'.", "severity": "High"})

        # 2. Content Check
        v81, v84, v11 = is_meaningful_content(d81 or ""), is_meaningful_content(d84 or ""), is_meaningful_content(d11 or "")
        m81_84 = check_match_triad(d81 or "", d84 or "") if (v81 and v84) else True
        m84_11 = check_match_triad(d84 or "", d11 or "") if (v84 and v11) else True
        m81_11 = check_match_triad(d81 or "", d11 or "") if (v81 and v11) else True

        if v81 and v84 and v11:
            if not m81_84 and not m84_11 and not m81_11:
                errors.append({"where": f"Sections 8.1, 8.4, 11 - {label}", "what": f"All sections have conflicting content for scenario {label}.", "suggestion": "Ensure content sync.", "severity": "High"})
            elif m84_11 and not m81_84:
                errors.append({"where": f"8.1. Number of Test Scenarios - {label}", "what": f"Section 8.1 content doesn't match 8.4/11 for scenario {label}.", "suggestion": "Sync 8.1 with 8.4/11.", "severity": "High"})
            elif m81_11 and not m81_84:
                errors.append({"where": f"8.4. Test Execution Steps - {label}", "what": f"Section 8.4 content doesn't match 8.1/11 for scenario {label}.", "suggestion": "Sync 8.4 with 8.1/11.", "severity": "High"})
            elif m81_84 and not m81_11:
                errors.append({"where": f"11. Test Execution - {id11}", "what": f"Section 11 content doesn't match 8.1/8.4 for scenario {label}.", "suggestion": "Sync 11 with 8.1/8.4.", "severity": "High"})
        elif v81 and v84 and not m81_84:
            errors.append({"where": f"8.4. Test Execution Steps - {label}", "what": f"Section 8.4 doesn't match 8.1 for scenario {label}.", "suggestion": "Sync with 8.1.", "severity": "High"})
        elif v84 and v11 and not m84_11:
            errors.append({"where": f"11. Test Execution - {id11}", "what": f"Section 11 doesn't match 8.4 for scenario {label}.", "suggestion": "Sync with 8.4.", "severity": "High"})
        elif v81 and v11 and not m81_11:
            errors.append({"where": f"11. Test Execution - {id11}", "what": f"Section 11 doesn't match 8.1 for scenario {label}.", "suggestion": "Sync with 8.1.", "severity": "High"})

        # Missing checks
        if d84 is None and d81 is not None:
            errors.append({"where": f"8.4. Test Execution Steps - {label}", "what": f"Missing scenario {label} in 8.4.", "suggestion": "Add to 8.4.", "severity": "High"})
        if d11 is None and d81 is not None:
            errors.append({"where": f"11. Test Execution - {label}", "what": f"Missing scenario {label} in 11.", "suggestion": "Add to 11.", "severity": "High"})
    
    return errors


def check_section_4(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'dut' in s.get('title', '').lower() and 'confirmation' in s.get('title', '').lower()), None)
    standard_title = "4. DUT Confirmation Details"
    if not target: return [{"where": standard_title, "what": "Section 4 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    
    found_table = False
    content = target.get('dut_details', []) + target.get('content', [])
    for it in content:
        if isinstance(it, dict) and it.get('type') == 'table':
            found_table = True
            headers = [str(h).strip().lower() for h in it.get('headers', [])]
            expected = ["interfaces", "ports", "type", "name"]
            for exp in expected:
                if not any(exp in h for h in headers):
                    errors.append({"where": f"{standard_title} - Table", "what": f"Column '{exp}' might be missing", "suggestion": f"Ensure headers strictly follow template.", "redirect_text": target.get('title'), "severity": "Medium"})
            break
    if not found_table:
        errors.append({"where": standard_title, "what": "Interface table missing", "suggestion": "Add DUT Interface details table.", "redirect_text": target.get('title'), "severity": "High"})
    return errors

def check_section_5(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'dut' in s.get('title', '').lower() and 'configuration' in s.get('title', '').lower()), None)
    standard_title = "5. DUT Configuration:"
    if not target: return [{"where": standard_title, "what": "Section 5 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    content = target.get('dut_configuration', []) + target.get('content', [])
    if not any(is_meaningful_content(it if isinstance(it, str) else it.get('text', '')) for it in content):
        errors.append({"where": standard_title, "what": "Content missing", "suggestion": "Provide DUT configuration details.", "redirect_text": target.get('title'), "severity": "High"})
    return errors

def check_section_6(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'precondition' in s.get('title', '').lower()), None)
    standard_title = "6. Preconditions"
    if not target: return [{"where": standard_title, "what": "Section 6 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    content = target.get('preconditions', []) + target.get('content', [])
    has_valid = any((isinstance(it, dict) and it.get('type') == 'image') or is_meaningful_content(it if isinstance(it, str) else it.get('text', '')) for it in content)
    if not has_valid:
        errors.append({"where": standard_title, "what": "Content missing", "suggestion": "Provide preconditions details or image.", "redirect_text": target.get('title'), "severity": "High"})
    return errors

def check_section_7(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'test' in s.get('title', '').lower() and 'objective' in s.get('title', '').lower()), None)
    standard_title = "7. Test Objective"
    if not target: return [{"where": standard_title, "what": "Section 7 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    content = target.get('test_objective', []) + target.get('content', [])
    if not any(is_meaningful_content(it if isinstance(it, str) else it.get('text', '')) for it in content):
        errors.append({"where": standard_title, "what": "Content missing", "suggestion": "Provide test objectives.", "redirect_text": target.get('title'), "severity": "High"})
    return errors

def check_section_8(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'test' in s.get('title', '').lower() and 'plan' in s.get('title', '').lower() and not re.search(r'\d+\.\d+', s.get('title', ''))), None)
    standard_title = "8. Test Plan"
    if not target: return [{"where": standard_title, "what": "Section 8 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    content = target.get('test_plan', []) + target.get('content', [])
    if not any(is_meaningful_content(it if isinstance(it, str) else it.get('text', '')) for it in content):
        errors.append({"where": standard_title, "what": "Intro content missing", "suggestion": "Add test plan summary.", "redirect_text": target.get('title'), "severity": "High"})
    return errors

def check_section_8_1(sections: List[Dict], global_base: str) -> List[Dict]:
    errors = []
    standard_title = "8.1. Number of Test Scenarios"
    redirect_stable = "Number of Test Scenarios"
    target_section = None
    for section in sections:
        title = str(section.get('title', '')).strip().replace('\n', ' ')
        title_lower = title.lower()
        if 'number' in title_lower and 'test' in title_lower and 'scenario' in title_lower and '8.1' in title_lower:
            target_section = section
            break

    if not target_section:
        return [{"where": standard_title, "what": "Section 8.1 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]

    found_title = target_section.get('title', '').strip().replace('\n', ' ')
    title_lower = found_title.lower()
    
    # Title Validation
    num_prefix_match = re.match(r'^(\d+[\.\s\d]*)\s*', found_title)
    has_correct_num = found_title.startswith("8.1.")
    if not has_correct_num:
        error_details = []
        if num_prefix_match:
            wrong_num = num_prefix_match.group(1).strip()
            error_details.append(f"Wrong section number (Found: '{wrong_num}', Expected: '8.1.')")
        else:
            error_details.append(f"Section number is missing (Found: '{found_title}')")
        
        if error_details:
            errors.append({
                "where": standard_title,
                "what": "Section title is incorrect. " + " ".join(error_details),
                "suggestion": f"Fix the title to exactly match: '{standard_title}'",
                "redirect_text": found_title,
                "severity": "Low"
            })

    # Content Validation
    actual_redirect = re.sub(r'^[\d\.]+\s*', '', found_title).replace(':', '').strip() or redirect_stable
    test_id_pattern = re.compile(r'(\d+(?:\s*[\. ]\s*\d+){3,})')
    
    scenarios_in_json = target_section.get('test_scenarios', [])
    content_items = target_section.get('content', [])
    parsed_scenarios = []
    
    if scenarios_in_json:
        for item in scenarios_in_json:
            if isinstance(item, dict):
                h = item.get('test_scenario', '')
                d = item.get('description', '')
                h_str = " ".join([str(i) for i in h if i]).strip() if isinstance(h, list) else str(h).strip()
                d_str = " ".join([str(i) for i in d if i]).strip() if isinstance(d, list) else str(d).strip()
                parsed_scenarios.append({'header': h_str, 'desc': d_str})
            else:
                parsed_scenarios.append({'header': str(item).strip(), 'desc': ''})
    else:
        raw_blocks = []
        for item in content_items:
            txt = item.get('text', '') if isinstance(item, dict) else str(item)
            if txt.strip(): raw_blocks.append(txt.strip())
        full_text = " ".join(raw_blocks)
        parts = re.split(r'(?=\b\d+(?:\s*[. ]\s*\d+){3,}\b)', full_text)
        for p in parts:
            p = p.strip()
            if not p: continue
            m = test_id_pattern.search(p)
            if m:
                idx_m = m.start()
                parsed_scenarios.append({'header': p[:idx_m+len(m.group(0))].strip(), 'desc': p[idx_m+len(m.group(0)):].strip()})
            else:
                if parsed_scenarios: parsed_scenarios[-1]['desc'] += " " + p
                else: parsed_scenarios.append({'header': '', 'desc': p})

    if not parsed_scenarios:
        errors.append({"where": standard_title, "what": "test scenario content missing.", "suggestion": "Add test scenarios.", "redirect_text": actual_redirect, "severity": "High"})
    else:
        # Internal base id discovery
        local_base = global_base
        if (not local_base or local_base == "1.1.1"):
            counts = {}
            for s in parsed_scenarios:
                m = test_id_pattern.search(s.get('header', ''))
                if m:
                    fid = re.sub(r'\s+', '', m.group(1)); parts = fid.split('.')
                    if len(parts) >= 3:
                         b = ".".join(parts[:3]); counts[b] = counts.get(b, 0) + 1
            if counts: local_base = max(counts, key=counts.get)

        for pos, item in enumerate(parsed_scenarios, 1):
            header, desc = item['header'], item['desc']
            id_match = test_id_pattern.search(header)
            
            tid = re.sub(r'\s+', '', id_match.group(1)) if id_match else ""
            where_ref = f"{standard_title} - Test Scenario {tid or pos}"
            redirect_text = normalize_redirect_text(f"{header} {desc}")
            
            sc_errs = []
            if id_match:
                exp_id = f"{local_base}.{pos}"
                if tid != exp_id:
                    sc_errs.append(f"test scenario id wrong. Found '{tid}', Expected: '{exp_id}'")
                
                # Prefix check
                pre = header[:id_match.start()].strip()
                if not re.fullmatch(r'(?:TestScenario|Test\s+Scenario)', pre, re.IGNORECASE):
                    sc_errs.append(f"incorrect prefix format: Found '{pre}', Expected: 'Test Scenario'")
            else:
                sc_errs.append("test scenario id missing.")
                
            if not is_meaningful_content(desc) and not is_meaningful_content(header[id_match.end():] if id_match else ""):
                sc_errs.append("test scenario content missing. Add technical description.")
                
            if sc_errs:
                errors.append({"where": where_ref, "what": " | ".join(sc_errs), "suggestion": f"Fix Scenario {pos} alignment", "redirect_text": redirect_text, "severity": "High" if "missing" in str(sc_errs) else "Low"})
    return errors

def check_section_8_2(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if all(k in s.get('title', '').lower() for k in ['test', 'bed', 'diagram'])), None)
    standard_title = "8.2. Test Bed Diagram"
    if not target: return [{"where": standard_title, "what": "Section 8.2 missing", "suggestion": f"Expected: '{standard_title}'", "redirect_text": "Test Bed Diagram", "severity": "High"}]
    
    found_title = str(target.get('title', '')).strip()
    if not found_title.startswith("8.2."):
         errors.append({"where": standard_title, "what": f"Wrong section number. Found: '{found_title.split(' ')[0]}'", "suggestion": "Expected: '8.2.'", "redirect_text": found_title, "severity": "Low"})
    
    content = target.get('content', [])
    images = [it for it in content if isinstance(it, dict) and it.get('type') == 'image']
    if not images:
        errors.append({"where": standard_title, "what": "Test Bed Diagram image is missing.", "suggestion": "Add diagram image.", "redirect_text": found_title, "severity": "High"})
    
    fig_pattern = re.compile(r'^[Ff]igure\s+([\d\.]+)\s*([-–: ])\s*(.*)$', re.IGNORECASE)
    expected_prefix = "8.2"
    img_count = 0
    for i, item in enumerate(content):
        if isinstance(item, dict) and item.get('type') == 'image':
            img_count += 1
            exp_id = f"{expected_prefix}.{img_count}"
            exp_name = "Test Bed Diagram" if len(images) == 1 else f"Test Bed Diagram {img_count}"
            
            caption = ""
            for j in range(i + 1, len(content)):
                text = content[j].get('text', '').strip() if isinstance(content[j], dict) else str(content[j]).strip()
                if not text: continue
                if fig_pattern.match(text): caption = text; break
                else: break
            
            if not caption:
                errors.append({"where": f"{standard_title} - Figure Check", "what": "Figure caption is missing under the diagram.", "suggestion": f"Add caption: 'Figure {exp_id}: {exp_name}'", "redirect_text": found_title, "severity": "High"})
            else:
                m = fig_pattern.match(caption)
                found_id = m.group(1).strip('.')
                found_name = (m.group(3) or "").strip()
                cap_errs = []
                if found_id != exp_id: cap_errs.append(f"Incorrect Figure ID: Found '{found_id}', Expected: '{exp_id}'")
                if not all(k in found_name.lower() for k in ['test', 'bed', 'diagram']):
                    cap_errs.append(f"Incorrect Figure Name format: Found '{found_name}'")
                
                m_seq = re.search(r'(\d+)$', found_name)
                if len(images) == 1 and m_seq: cap_errs.append(f"Unnecessary number suffix '{m_seq.group(1)}'")
                elif len(images) > 1:
                    if not m_seq or int(m_seq.group(1)) != img_count:
                        cap_errs.append(f"Sequence mismatch in name: Found '{m_seq.group(1) if m_seq else 'None'}', Expected: '{img_count}'")
                
                if cap_errs:
                    errors.append({"where": f"{standard_title} - Figure Check", "what": "Caption is wrong: " + " | ".join(cap_errs), "suggestion": f"Expected: 'Figure {exp_id}: {exp_name}'", "redirect_text": found_title, "severity": "Medium"})
    return errors

def check_section_8_3(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'tools' in s.get('title', '').lower() and 'required' in s.get('title', '').lower()), None)
    standard_title = "8.3. Tools Required"
    if not target: return [{"where": standard_title, "what": "Section 8.3 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    
    tools = target.get('tools', [])
    if not tools or not any(is_meaningful_content(t.get('tool', '')) for t in tools):
        errors.append({"where": standard_title, "what": "Tools list empty", "suggestion": "List required tools with versions.", "redirect_text": target.get('title'), "severity": "High"})
    else:
        for i, tool in enumerate(tools, 1):
            name = str(tool.get('tool', ''))
            version = str(tool.get('version', ''))
            # If version is empty, check if it's already in the name string
            if not is_meaningful_content(version):
                if not re.search(r'\bv\b|\bversion\b|\d+\.\d+', name, re.IGNORECASE):
                    errors.append({"where": f"{standard_title} - Tool {i}", "what": f"Version missing in '{name}'", "suggestion": "Add version (e.g., v 1.0).", "redirect_text": target.get('title'), "severity": "Medium"})
    return errors

def check_section_8_4(sections: List[Dict], global_base: str) -> List[Dict]:
    errors = []
    target = next((s for s in sections if any(x in s.get('title', '').lower() for x in ["test execution step", "testexecutionstep"])), None)
    standard_title = "8.4. Test Execution Steps"
    if not target: return [{"where": standard_title, "what": "Section 8.4 missing", "suggestion": f"Expected: '{standard_title}'", "redirect_text": "Test Execution Steps", "severity": "High"}]
    
    sources = target.get('execution_steps', target.get('test_steps', []))
    test_id_pattern = re.compile(r'(\d+[\d\.\s]*\d+)')
    
    # Internal base id discovery
    local_base = global_base
    if (not local_base or local_base == "1.1.1") and sources:
        counts = {}
        for s in sources:
            m = test_id_pattern.search(s.get('test_scenario', s.get('text', '')))
            if m:
                fid = re.sub(r'\s+', '', m.group(1))
                parts = fid.split('.')
                if len(parts) >= 3:
                     b = ".".join(parts[:3]); counts[b] = counts.get(b, 0) + 1
        if counts: local_base = max(counts, key=counts.get)

    for i, source in enumerate(sources, 1):
        text = source.get('test_scenario', source.get('text', ''))
        steps = source.get('steps', [])
        step_text = " ".join([str(s.get('step', '')) if isinstance(s, dict) else str(s) for s in steps])
        
        m = test_id_pattern.search(text)
        found_id = re.sub(r'\s+', '', m.group(1)) if m else ""
        exp_id = f"{local_base}.{i}"
        where_ref = f"{standard_title} - Test Scenario {found_id or i}"
        redirect_text = normalize_redirect_text(f"{text} {step_text}")
        
        sc_errs = []
        if m:
            if found_id != exp_id:
                sc_errs.append(f"test scenario id wrong. Found '{found_id}', Expected: '{exp_id}'")
            
            m_pre = re.search(r'^(.*?)(?:\d+[\d\.\s]*\d+)', text)
            pre = m_pre.group(1).strip() if m_pre else ""
            if not re.fullmatch(r'(?:TestScenario|Test\s+Scenario)', pre, re.IGNORECASE):
                sc_errs.append(f"incorrect prefix format: Found '{pre}', Expected: 'Test Scenario'")
        else:
            sc_errs.append("test scenario id missing.")
            
        if not is_meaningful_content(step_text):
            sc_errs.append("test scenario content missing. Add execution steps.")
            
        if sc_errs:
            errors.append({"where": where_ref, "what": " | ".join(sc_errs), "suggestion": f"Fix Scenario {i} to match sequence {exp_id}", "redirect_text": redirect_text, "severity": "High" if "missing" in str(sc_errs) else "Low"})
    return errors

def check_section_9(sections: List[Dict], global_base: str) -> List[Dict]:
    errors = []
    expected9_title = "9. Expected Results for Pass:"
    redirect_title = "Expected Results for Pass"
    test_id_pattern = re.compile(r'\b(\d+(?:\s*[. ]\s*\d+){3})\b')

    # Find Section 9 by keywords
    target_idx = -1
    found_title = ""
    for idx, sec in enumerate(sections):
        title = sec.get('title', '').strip()
        if 'expected' in title.lower() and 'result' in title.lower() and ('9.' in title or title.startswith('9')):
            target_idx = idx
            found_title = title
            break

    if target_idx == -1:
        return [{"where": expected9_title, "what": "Section 9 missing", "suggestion": f"Expected: '{expected9_title}'", "redirect_text": redirect_title, "severity": "High"}]

    target = sections[target_idx]

    # --- TITLE VALIDATION ---
    title_lower = found_title.lower()
    num_match = re.match(r'^([\d\.]+)', found_title)
    has_any_number = num_match is not None
    has_correct_num = found_title.startswith("9.")
    actual_prefix = num_match.group(1).strip() if num_match else "9"
    display_title = f"{actual_prefix} {expected9_title.split(' ', 1)[1]}"

    if not (has_correct_num and "expected results for pass" in title_lower):
        if has_any_number and not has_correct_num:
            errors.append({
                "where": display_title,
                "what": f"Wrong section number in the title. Found: '{actual_prefix}', Expected: '9.'",
                "suggestion": f"Replace section number '{actual_prefix}' with '9.'. Expected: '{expected9_title}'",
                "redirect_text": found_title, "severity": "Low"
            })
        elif not has_any_number:
            errors.append({
                "where": display_title,
                "what": f"Section number is missing in the title. Found: '{found_title}'",
                "suggestion": f"Add the section number prefix. Expected: '{expected9_title}'",
                "redirect_text": found_title, "severity": "Medium"
            })
        if "expected results for pass" not in title_lower:
            is_space_issue = any(p in title_lower for p in ["resultsfor", "expectedresults", "9.."])
            what_msg = (f"Incorrect formatting (space issue) in the title. Found: '{found_title}'"
                        if is_space_issue else f"Incorrect formatting in the title. Found: '{found_title}'")
            errors.append({
                "where": display_title, "what": what_msg,
                "suggestion": f"Fix the title to exactly match: '{expected9_title}'",
                "redirect_text": found_title, "severity": "Low"
            })

    actual_redirect = found_title if found_title else redirect_title

    # --- CONTENT PARSING ---
    # First check target section for structured/unstructured
    er_items = target.get('expected_results', [])
    content_items = target.get('content', [])
    parsed_scenarios = []

    def parse_from_content(items):
        results = []
        raw_blocks = [item.get('text', '') if isinstance(item, dict) else str(item) for item in items]
        full_text = " ".join([b.strip() for b in raw_blocks if b.strip()])
        # Detect scenario starts
        parts = re.split(r'(?=\b[Tt]est\s+[Ss]cenario|\d+(?:\s*[. ]\s*\d+){3}\b)', full_text)
        for p in parts:
            p = p.strip()
            if not p: continue
            m = test_id_pattern.search(p)
            if m:
                raw_id = m.group(1)
                id_pos = p.find(raw_id)
                header_part = p[:id_pos + len(raw_id)].strip()
                desc_part = p[id_pos + len(raw_id):].strip()
                results.append({'header': header_part, 'desc': desc_part})
            else:
                if results: results[-1]['desc'] += " " + p
                else: results.append({'header': '', 'desc': p})
        return results

    if er_items:
        for x in er_items:
            if isinstance(x, dict):
                h_val = x.get('test_case_id', '')
                h = " ".join([str(i) for i in h_val if i]).strip() if isinstance(h_val, list) else str(h_val).strip()
                d_val = x.get('expected_result', '')
                d = " ".join([str(i) for i in d_val if i]).strip() if isinstance(d_val, list) else str(d_val).strip()
                parsed_scenarios.append({'header': h, 'desc': d})
            else:
                parsed_scenarios.append({'header': str(x).strip(), 'desc': ''})
    else:
        parsed_scenarios.extend(parse_from_content(content_items))

    # COLLATERAL SCAN: If parsed_scenarios is still empty (or as a safety measure),
    # check subsequent level-2 sections until the next level-1 section
    for i in range(target_idx + 1, len(sections)):
        s = sections[i]
        if s.get('level', 1) == 1: break # Stop at next high-level section
        
        s_content = s.get('content', [])
        s_er = s.get('expected_results', [])
        if s_er:
             # Already structured by LLM parser elsewhere
             for x in s_er:
                if isinstance(x, dict):
                    parsed_scenarios.append({'header': str(x.get('test_case_id', '')), 'desc': str(x.get('expected_result', ''))})
        else:
             sub_parsed = parse_from_content(s_content)
             # Only add if it actually looks like a scenario
             if any(test_id_pattern.search(p['header']) for p in sub_parsed):
                 parsed_scenarios.extend(sub_parsed)

    if not parsed_scenarios:
        errors.append({"where": expected9_title, "what": "Expected results content missing.", "suggestion": "Add expected result entries with Test Scenario IDs.", "redirect_text": actual_redirect, "severity": "High"})
        return errors

    # --- SCENARIO VALIDATION ---
    pos_errors = []
    # Clean up empty headers/descriptions
    valid_scenarios = [p for p in parsed_scenarios if test_id_pattern.search(p['header'])]
    
    for position, item in enumerate(valid_scenarios, 1):
        header, desc = item['header'], item['desc']
        combined = (header + " " + desc).strip()

        # Space check
        if re.search(r'TestScenario', header, re.IGNORECASE):
            pos_errors.append({
                "pos": position,
                "where": f"{display_title} - Test Scenario {position}",
                "what": "Incorrect format: Found 'TestScenario' (missing space)",
                "suggestion": "Expected: 'Test Scenario'",
                "redirect_text": actual_redirect, "severity": "Low"
            })

        id_match = test_id_pattern.search(combined)
        exp_id = f"{global_base}.{position}"
        # Extract ID for display if possible
        found_id_raw = re.sub(r'[\s]+', '', id_match.group(1)) if id_match else f"#{position}"
        where_ref = f"{display_title} - {found_id_raw}"

        if not id_match:
            pos_errors.append({"pos": position, "where": where_ref, "what": f"ID missing in test scenario {position}", "suggestion": f"Expected: 'Test Scenario {exp_id}:'", "redirect_text": actual_redirect, "severity": "Medium"})
            continue

        raw_id_text = id_match.group(1)
        found_id = re.sub(r'[\s]+', '', raw_id_text)
        found_parts = found_id.split('.')
        found_base = ".".join(found_parts[:-1]) if len(found_parts) > 1 else ""
        found_seq = found_parts[-1] if found_parts else ""

        is_base_wrong = global_base and found_base != global_base
        is_seq_wrong = found_seq != str(position)

        if is_base_wrong or is_seq_wrong:
            reason = " (Alignment mismatch)" if is_seq_wrong else ""
            pos_errors.append({"pos": position, "where": where_ref, "what": f"test scenario id wrong. Found '{found_id}'.{reason}", "suggestion": f"Expected: {exp_id}", "redirect_text": actual_redirect, "severity": "Low"})

        # Content check
        content_part = re.sub(r'^[:\.\s]+', '', combined[combined.find(raw_id_text) + len(raw_id_text):].strip())
        if not is_meaningful_content(content_part):
            pos_errors.append({"pos": position, "where": where_ref, "what": f"test scenario expected result missing. Found ID '{found_id}'.", "suggestion": f"Add expected result for Scenario {found_id}", "redirect_text": actual_redirect, "severity": "High"})

    # Sort and final errors
    severity_map = {"High": 0, "Medium": 1, "Low": 2}
    pos_errors.sort(key=lambda x: (x.get("pos", 0), severity_map.get(x.get("severity", "Low").capitalize(), 2)))
    for e in pos_errors:
        e.pop("pos", None)
        errors.append(e)
    return errors

def check_section_10(sections: List[Dict]) -> List[Dict]:
    errors = []
    target = next((s for s in sections if 'expected' in s.get('title', '').lower() and 'format' in s.get('title', '').lower() and 'evidence' in s.get('title', '').lower()), None)
    standard_title = "10. Expected Format of Evidence:"
    if not target: return [{"where": standard_title, "what": "Section 10 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    content = target.get('expected_format_of_evidence', []) + target.get('content', [])
    if not any(is_meaningful_content(it if isinstance(it, str) else it.get('text', '')) for it in content):
        errors.append({"where": standard_title, "what": "Content missing", "suggestion": "Provide format details.", "redirect_text": target.get('title'), "severity": "High"})
    return errors

def check_section_11(sections: List[Dict], global_base: str) -> Tuple[List[Dict], Dict]:
    errors = []
    pipeline_data = {}
    standard_title = "11. Test Execution"
    main_section = next((s for s in sections if 'test' in s.get('title', '').lower() and 'execution' in s.get('title', '').lower()), None)
    if not main_section: 
        return [{"where": standard_title, "what": "Section 11 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}], {}

    # Filter for sub-sections like 11.1.1, 11.1.2 (must have a digit after the dot)
    tc_sections = [s for s in sections if re.match(r'^11\.\d\.\d', str(s.get('title', '')))]
    
    # Validation: Ensure we don't accidentally pick the main section again or other sections
    tc_sections = [s for s in tc_sections if "test case number" in str(s.get('title', '')).lower()]
    
    if not tc_sections:
        if not main_section.get('content'):
            return [{"where": standard_title, "what": "Subsections missing", "suggestion": "Add test case detailed sections (11.1.1, 11.1.2...).", "severity": "High"}], {}
        return [], {}

    for i, sec in enumerate(tc_sections, 1):
        title = str(sec.get('title', ''))
        exp_tc_num = f"11.1.{i}"
        exp_id = f"{global_base}.{i}"
        where_base = f"{standard_title} - {exp_tc_num}"
        
        tc_pipeline_key = f"test_case_id_{exp_id}"
        tc_pipeline_entry = {
            "test_case_name": "",
            "test_case_description": "",
            "execution": "",
            "test_observation": "",
            "evidence_provided": "",
            "figure_number": ""
        }
        
        if exp_tc_num not in title:
            errors.append({"where": where_base, "what": f"Wrong TC number (Found: {title.split(' ')[0]})", "suggestion": f"Expected: {exp_tc_num}", "redirect_text": title, "severity": "Low"})
            
        content = sec.get('content', []) + sec.get('itsar_section_details', [])
        content_items = [it if isinstance(it, str) else it.get('text', '') if isinstance(it, dict) and it.get('type') != 'image' else it for it in content]
        text_only = [str(t) for t in content_items if isinstance(t, str) and t.strip()]
        
        # ID Validation
        m = re.search(r'(\d+\.\d+\.\d+\.\d+)', " ".join(text_only))
        if m and m.group(1) != exp_id:
            msg = f"ID mismatch ({m.group(1)})"
            errors.append({"where": where_base, "what": msg, "suggestion": f"Expected: {exp_id}", "redirect_text": title, "severity": "Low"})
            
        # Subsection Validation (a-e)
        sub_errs, _ = check_itsar_subsections(text_only)
        label_to_key = {
            "a. Test Case Name": "test_case_name",
            "b. Test Case Description": "test_case_description",
            "c. Execution Steps": "execution",
            "d. Test Observations": "test_observation",
            "e. Evidence Provided": "evidence_provided"
        }
        
        for se in sub_errs:
            errors.append({"where": f"{where_base} - {se['label']}", "what": se['why'], "suggestion": se['suggestion'], "redirect_text": title, "severity": se['severity']})
            key = label_to_key.get(se['label'])
            if key:
                tc_pipeline_entry[key] = se['why']
        
        # Figure ID Sequence Validation
        fig_errs = check_section_11_figures(content, exp_tc_num)
        fig_err_msgs = []
        for fe in fig_errs:
            errors.append({"where": where_base, "what": fe['why'], "suggestion": fe['suggestion'], "redirect_text": title, "severity": fe['severity']})
            fig_err_msgs.append(fe['why'])
        
        if fig_err_msgs:
            tc_pipeline_entry["figure_number"] = " | ".join(fig_err_msgs)
            
        # Filter: only keep fields that have actual error messages
        filtered_entry = {k: v for k, v in tc_pipeline_entry.items() if v}
        if filtered_entry:
            pipeline_data[tc_pipeline_key] = filtered_entry

    return errors, pipeline_data

def check_section_12(sections: List[Dict], global_base: str) -> List[Dict]:
    errors = []
    target = next((s for s in sections if all(k in s.get('title', '').lower() for k in ["12", "test", "case", "result"])), None)
    standard_title = "12. Test Case Result:"
    if not target: return [{"where": standard_title, "what": "Section 12 missing", "suggestion": f"Expected: '{standard_title}'", "severity": "High"}]
    
    actual_title = target.get('title', '').strip()
    redirect_title = re.sub(r'^[\d\.]+\s*', '', actual_title).strip() or "Test Case Result"
    
    # Title validation
    if not actual_title.startswith("12."):
        errors.append({"where": standard_title, "what": f"Wrong section number. Found: '{actual_title.split(' ')[0]}'", "suggestion": "Expected: '12.'", "redirect_text": redirect_title, "severity": "Low"})
    
    results = target.get('test_case_results', {})
    headers = results.get('headers', [])
    rows = results.get('rows', [])
    
    if not headers:
        errors.append({"where": standard_title, "what": "Table headers missing", "suggestion": "Expected: ['Sr. No', 'TEST CASE No.', 'PASS/ FAIL', 'Remarks']", "redirect_text": redirect_title, "severity": "High"})
    else:
        # Header validation
        h_map = {
            0: {"expected": ["s. no", "sr. no", "s no", "sr no"], "label": "Sr. No"},
            1: {"expected": ["test case no", "test case number", "tc no"], "label": "TEST CASE No."},
            2: {"expected": ["pass fail", "status", "result", "/"], "label": "PASS/ FAIL"},
            3: {"expected": ["remarks", "remark", "observation"], "label": "Remarks"}
        }
        for idx, info in h_map.items():
            if idx < len(headers):
                h_val = str(headers[idx]).lower().strip()
                if not any(e in h_val for e in info['expected']):
                    errors.append({"where": f"{standard_title} - Column #{idx+1}", "what": f"Incorrect table header: Found '{headers[idx]}'", "suggestion": f"Expected: '{info['label']}'", "redirect_text": redirect_title, "severity": "Medium"})

    if not rows:
        errors.append({"where": standard_title, "what": "Results table empty", "suggestion": "Add test results to table.", "redirect_text": redirect_title, "severity": "High"})
    else:
        for ridx, row in enumerate(rows, 1):
            if len(row) < 4:
                errors.append({"where": f"{standard_title} - Row #{ridx}", "what": f"Incomplete row data: Found {len(row)} columns.", "suggestion": "Ensure each row has at least 4 columns (S.No, ID, Status, Remarks)", "redirect_text": redirect_title, "severity": "Medium"})
                continue
            
            s_no = str(row[0]).strip()
            tc_id = str(row[1]).strip()
            status_raw = str(row[2]).strip().upper().replace('\n', ' ')
            status = re.sub(r'\s+', ' ', status_raw)
            remarks = str(row[3]).strip()
            
            expected_tc_id = f"{global_base}.{ridx}"
            entry_ref = f"{standard_title} - Row #{ridx}"
            
            # 1. Serial Number Check (Index 0)
            if not s_no:
                errors.append({"where": entry_ref, "what": "S. No missing in 'S. No' column: Found empty.", "suggestion": f"Expected: '{ridx}'", "redirect_text": redirect_title, "severity": "High"})
            elif s_no != str(ridx):
                errors.append({"where": entry_ref, "what": f"Incorrect sequence order in S. No column: Found '{s_no}'.", "suggestion": f"Expected: '{ridx}'", "redirect_text": redirect_title, "severity": "Low"})
            
            # 2. Test Case ID Check (Index 1)
            if not tc_id:
                errors.append({"where": entry_ref, "what": "Test case ID missing: Found empty in 'TEST CASE No.' column.", "suggestion": f"Expected: '{expected_tc_id}'", "redirect_text": redirect_title, "severity": "High"})
            elif tc_id != expected_tc_id:
                is_base_mismatch = global_base and not tc_id.startswith(global_base)
                msg_type = "Base ID mismatch" if is_base_mismatch else "Incorrect sequence order"
                errors.append({"where": entry_ref, "what": f"{msg_type} in TEST CASE No. column: Found '{tc_id}'.", "suggestion": f"Expected: '{expected_tc_id}'", "redirect_text": redirect_title, "severity": "Low"})
            
            # 3. Status Validation (Index 2)
            if not status:
                errors.append({"where": entry_ref, "what": "Result status missing in 'PASS FAIL' column: Found empty.", "suggestion": "Expected: PASS/FAIL/NA/AVERAGE", "redirect_text": redirect_title, "severity": "High"})
            elif status not in ["PASS", "FAIL", "NA", "NOT APPLICABLE", "AVERAGE", "PASS/FAIL", "PASS / FAIL"]:
                errors.append({"where": entry_ref, "what": f"Invalid status: Found '{status}'.", "suggestion": "Expected: PASS, FAIL, NA, or AVERAGE", "redirect_text": redirect_title, "severity": "Medium"})
            
            # 4. Remarks Validation (Index 3)
            if not remarks or remarks in ['.', '...', ':', '-', 'NA']:
                errors.append({"where": entry_ref, "what": "Remarks missing or non-meaningful.", "suggestion": "Add detailed technical observations.", "redirect_text": redirect_title, "severity": "Medium"})
    
    return errors

# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Full Audit Engine")
    parser.add_argument("json_file", type=str, help="Path to structured document JSON file")
    parser.add_argument(
        "requirement_file", type=str, nargs="?", default=None,
        help="Optional: Path to requirement.json as second positional argument"
    )
    parser.add_argument(
        "--requirement", "-a", type=str, default=None,
        help="Optional: Path to requirement.json via flag (overrides positional if both given)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="output.json",
        help="Optional: Path to output JSON file (default: output.json)"
    )
    args = parser.parse_args()
    # Resolve: --requirement flag > positional requirement_file > auto-detect
    args.requirement = args.requirement or args.requirement_file

    
    if not os.path.exists(args.json_file):
        print(json.dumps([{"where": "System", "what": "File not found", "severity": "High"}]))
        sys.exit(1)

    try:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sections = data.get('sections', [])

        # --- Base ID Resolution ---
        # Priority: (1) --requirement flag  (2) auto-detect requirement.json next to main.py  (3) document scan
        global_base = None

        # Determine requirement.json path to try
        requirement_path = None
        if args.requirement:
            requirement_path = args.requirement
        else:
            # Auto-detect: look for requirement.json in same folder as this script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(script_dir, "requirement.json")
            if os.path.exists(candidate):
                requirement_path = candidate

        if not requirement_path or not os.path.exists(requirement_path):
            print(json.dumps([{"where": "System", "what": f"requirement.json not found (or path is empty)", "severity": "High"}]))
            sys.exit(1)
        
        try:
            with open(requirement_path, 'r', encoding='utf-8') as f:
                requirement_cfg = json.load(f)
            clause_name = requirement_cfg.get("clause_name", "")
            # Extract X.Y.Z from "1.1.1..."
            m = re.search(r'(\d+\.\d+\.\d+)', clause_name)
            if m:
                global_base = m.group(1)
        except Exception:
            pass

        if not global_base:
            print(json.dumps([{"where": "System", "what": "Base ID (e.g., 1.1.1) could not be resolved from requirement.json.", "suggestion": "Provide a valid 'clause_name' in requirement.json.", "severity": "High"}]))
            sys.exit(1)


        all_errors = []
        # Section 1, 2, 3 Checks
        all_errors.extend(check_section_1(sections, requirement_cfg))
        all_errors.extend(check_section_2(sections, requirement_cfg))
        all_errors.extend(check_section_3(sections, requirement_cfg))
        
        # Section 4-12 Checks
        all_errors.extend(check_section_4(sections))
        all_errors.extend(check_section_5(sections))
        all_errors.extend(check_section_6(sections))
        all_errors.extend(check_section_7(sections))
        all_errors.extend(check_section_8(sections))
        all_errors.extend(check_section_8_1(sections, global_base))
        all_errors.extend(check_section_8_2(sections))
        all_errors.extend(check_section_8_3(sections))
        all_errors.extend(check_section_8_4(sections, global_base))
        all_errors.extend(check_section_9(sections, global_base))
        all_errors.extend(check_section_10(sections))
        
        # Section 11 specific structured output
        sec11_errors, pipeline_sec11 = check_section_11(sections, global_base)
        all_errors.extend(sec11_errors)
        
        all_errors.extend(check_section_12(sections, global_base))

        # Test Scenario Match Issues (Triad Consistency Check (8.1, 8.4, 11))
        # Move this to the end as requested
        all_errors.extend(check_triad_consistency(sections))

        # Filter duplicates
        final_errors = []
        seen = set()
        for e in all_errors:
            key = (e.get('where'), e.get('what'))
            if key not in seen:
                final_errors.append(e)
                seen.add(key)

        # Store section 11 errors in pipeline_output.json in requested format
        pipeline_output = {
            "format_check": {
                "section_11": pipeline_sec11
            }
        }
        pipeline_file_path = os.path.join(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", "pipeline_output.json")
        with open(pipeline_file_path, 'w', encoding='utf-8') as f:
            json.dump(pipeline_output, f, indent=2)

        print(json.dumps(final_errors, indent=4))
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(final_errors, f, indent=4)
        
        if final_errors: sys.exit(1)
        else: sys.exit(0)

    except Exception as e:
        print(json.dumps([{"where": "System", "what": f"Crash: {str(e)}", "severity": "High"}]))
        sys.exit(1)

if __name__ == "__main__":
    main()
