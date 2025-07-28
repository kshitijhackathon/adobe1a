import json
from difflib import SequenceMatcher

def load_json(file_path):
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)

def section_key(section):
    # Key for matching: (document, section_title, page_number)
    return (
        section.get("document", "").strip(),
        section.get("section_title", "").strip(),
        str(section.get("page_number", "")).strip()
    )

def subsection_key(subsection):
    # Key for matching subsection: (document, section_title, page_number)
    return (
        subsection.get("document", "").strip(),
        subsection.get("section_title", "").strip(),
        str(subsection.get("page_number", "")).strip()
    )

def fuzzy_equal(a, b):
    # For refined_text, allow partial match (change threshold as needed)
    return SequenceMatcher(None, a, b).ratio() > 0.85

def compare_sections(ref_sections, user_sections):
    gold = {section_key(sec): sec for sec in ref_sections}
    pred = {section_key(sec): sec for sec in user_sections}

    missing = [k for k in gold if k not in pred]
    extra   = [k for k in pred if k not in gold]
    matched = [k for k in gold if k in pred]

    print(f"Sections: {len(matched)} matched, {len(missing)} missing, {len(extra)} extra")
    if missing:
        print("Missing sections (in reference, not in yours):")
        for k in missing:
            print("  -", k)
    if extra:
        print("Extra sections (in yours, not in reference):")
        for k in extra:
            print("  -", k)
    return len(matched), len(ref_sections), len(user_sections)

def compare_subsections(ref_subs, user_subs):
    gold = {(subsection_key(sub), sub.get("refined_text", "")) for sub in ref_subs}
    pred = {(subsection_key(sub), sub.get("refined_text", "")) for sub in user_subs}

    matched = 0
    for gkey, gtext in gold:
        for pkey, ptext in pred:
            if gkey == pkey and (gtext == ptext or fuzzy_equal(gtext, ptext)):
                matched += 1
                break

    missing = len(gold) - matched
    extra   = len(pred) - matched
    print(f"Subsections: {matched} matched, {missing} missing, {extra} extra")
    return matched, len(gold), len(pred)

def main():
    ref = load_json("challenge1b_output.json")
    out = load_json("output.json")
    print("\n=== Metadata Comparison ===")
    for k in ("persona", "job_to_be_done"):
        ref_meta, out_meta = ref["metadata"].get(k, ""), out["metadata"].get(k, "")
        print(f"{k}: {'MATCH' if ref_meta.strip() == out_meta.strip() else 'DIFFER'}")
    print()
    print("=== Extracted Sections ===")
    sm, sref, sout = compare_sections(ref["extracted_sections"], out["extracted_sections"])
    prec = sm / sout if sout else 0
    rec = sm / sref if sref else 0
    f1 = (2*prec*rec)/(prec+rec) if (prec+rec)>0 else 0
    print(f"Precision: {prec:.2%}  Recall: {rec:.2%}  F1: {f1:.2%}")
    print()
    print("=== Subsection Analysis ===")
    sm2, sref2, sout2 = compare_subsections(ref["subsection_analysis"], out["subsection_analysis"])
    prec2 = sm2 / sout2 if sout2 else 0
    rec2 = sm2 / sref2 if sref2 else 0
    f1_2 = (2*prec2*rec2)/(prec2+rec2) if (prec2+rec2)>0 else 0
    print(f"Precision: {prec2:.2%}  Recall: {rec2:.2%}  F1: {f1_2:.2%}")

if __name__ == "__main__":
    main()
