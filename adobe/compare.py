import json
import os
from pathlib import Path

def compare_single_file(mine_outline, adobe_outline):
    """Compare two outlines and return detailed metrics"""
    sa = {(o["level"], o["text"].strip(), o["page"]) for o in mine_outline}
    sb = {(o["level"], o["text"].strip(), o["page"]) for o in adobe_outline}
    
    only_in_mine = sa - sb
    only_in_adobe = sb - sa
    matches = sa & sb
    
    return {
        "only_in_mine": only_in_mine,
        "only_in_adobe": only_in_adobe,
        "matches": matches,
        "is_exact_match": len(only_in_mine) == 0 and len(only_in_adobe) == 0,
        "precision": len(matches) / len(sa) if sa else 0,
        "recall": len(matches) / len(sb) if sb else 0
    }

def compare_all_files():
    """Compare all PDF files between output and reference"""
    output_dir = "output"
    reference_dir = "."  # Current directory where reference files are
    
    # Find all JSON files in output directory
    output_files = [f for f in os.listdir(output_dir) if f.endswith('.json')]
    
    results = {}
    total_files = 0
    exact_matches = 0
    
    print("=" * 80)
    print("PDF OUTLINE EXTRACTION COMPARISON REPORT")
    print("=" * 80)
    
    for output_file in sorted(output_files):
        file_base = output_file.replace('.json', '')
        output_path = os.path.join(output_dir, output_file)
        reference_path = os.path.join(reference_dir, output_file)
        
        # Check if reference file exists
        if not os.path.exists(reference_path):
            print(f"⚠️  {file_base}: Reference file not found")
            continue
        
        try:
            # Load both files
            with open(output_path, "r", encoding="utf-8") as f1:
                mine = json.load(f1)
            with open(reference_path, "r", encoding="utf-8") as f2:
                adobe = json.load(f2)
            
            # Compare outlines
            comparison = compare_single_file(mine["outline"], adobe["outline"])
            results[file_base] = comparison
            total_files += 1
            
            # Print detailed results for each file
            print(f"\n📄 {file_base.upper()}")
            print("-" * 60)
            
            if comparison["is_exact_match"]:
                print("✅ PERFECT MATCH!")
                exact_matches += 1
            else:
                print("❌ Differences found:")
                
                if comparison["only_in_mine"]:
                    print(f"\n🔴 In YOUR output but NOT in Adobe ({len(comparison['only_in_mine'])} items):")
                    for item in sorted(comparison["only_in_mine"]):
                        level, text, page = item
                        print(f"   • {level}: '{text}' (page {page})")
                
                if comparison["only_in_adobe"]:
                    print(f"\n🔵 In Adobe but NOT in YOUR output ({len(comparison['only_in_adobe'])} items):")
                    for item in sorted(comparison["only_in_adobe"]):
                        level, text, page = item
                        print(f"   • {level}: '{text}' (page {page})")
                
                if comparison["matches"]:
                    print(f"\n✅ Correctly matched ({len(comparison['matches'])} items):")
                    for item in sorted(comparison["matches"]):
                        level, text, page = item
                        print(f"   • {level}: '{text}' (page {page})")
            
            # Performance metrics
            print(f"\n📊 Metrics:")
            print(f"   Precision: {comparison['precision']:.2%}")
            print(f"   Recall: {comparison['recall']:.2%}")
            if comparison['precision'] + comparison['recall'] > 0:
                f1_score = 2 * (comparison['precision'] * comparison['recall']) / (comparison['precision'] + comparison['recall'])
                print(f"   F1-Score: {f1_score:.2%}")
        
        except Exception as e:
            print(f"❗ Error processing {file_base}: {str(e)}")
    
    # Overall summary
    print("\n" + "=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    print(f"Total files processed: {total_files}")
    print(f"Exact matches: {exact_matches}")
    print(f"Success rate: {exact_matches/total_files:.2%}" if total_files > 0 else "No files processed")
    
    if total_files > 0:
        # Calculate average metrics
        avg_precision = sum(r["precision"] for r in results.values()) / len(results)
        avg_recall = sum(r["recall"] for r in results.values()) / len(results)
        avg_f1 = 2 * (avg_precision * avg_recall) / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0
        
        print(f"Average Precision: {avg_precision:.2%}")
        print(f"Average Recall: {avg_recall:.2%}")
        print(f"Average F1-Score: {avg_f1:.2%}")
        
        # Performance assessment
        if exact_matches == total_files:
            print("\n🎉 EXCELLENT: All files match perfectly!")
        elif avg_f1 >= 0.90:
            print("\n🟢 VERY GOOD: High accuracy achieved")
        elif avg_f1 >= 0.75:
            print("\n🟡 GOOD: Decent performance, room for improvement")
        else:
            print("\n🔴 NEEDS WORK: Significant improvements needed")
    
    return results

if __name__ == "__main__":
    results = compare_all_files()
