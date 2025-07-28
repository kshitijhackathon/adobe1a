from pathlib import Path
from datetime import datetime
import json

def main():
    print("=== Enhanced Round 1B: Persona-Driven Document Intelligence (Fixed Input/Output Paths) ===")

    input_dir = Path("/app/input")
    output_path = Path("./output.json")  # root directory inside container

    # Find JSON input file(s) in /app/input
    input_json_files = list(input_dir.glob("*.json"))
    if not input_json_files:
        print("No JSON input file found in /app/input. Exiting.")
        return
    elif len(input_json_files) > 1:
        print(f"Multiple JSON files found in /app/input, using the first one: {input_json_files[0].name}")

    json_input_path = input_json_files[0]
    print(f"Using input JSON: {json_input_path}")

    # Load JSON input
    json_data = load_json_input(str(json_input_path))
    if not json_data:
        print("Failed to load JSON input file. Exiting.")
        return

    # Extract persona and job information
    persona, job = extract_persona_and_job(json_data)
    if not persona or not job:
        print("Warning: Persona or job missing in JSON input")
        print(f"Persona: {persona}")
        print(f"Job: {job}")

    print(f"Persona: {persona}")
    print(f"Job: {job}")

    chunk_size = 25
    print(f"Processing PDF pages in chunks of {chunk_size} pages")

    # PDF files also in /app/input directory
    pdf_base_dir = input_dir
    pdf_files = extract_pdf_paths(json_data, pdf_base_dir)
    if not pdf_files:
        print(f"No PDF files found at {pdf_base_dir}. Check JSON keys and file existence.")
        return

    print(f"Found {len(pdf_files)} PDF file(s) to process...")

    processor = MemoryEfficientDocumentProcessor(chunk_size=chunk_size)

    all_sections = []
    processed_documents = []

    for pdf_file in pdf_files:
        print(f"\nProcessing: {pdf_file.name}")
        section_count = 0
        try:
            for section in processor.extract_sections_generator(str(pdf_file)):
                all_sections.append(section)
                section_count += 1
                if section_count % 50 == 0:
                    print(f"  Extracted {section_count} sections...")
            processed_documents.append(pdf_file.name)
            print(f"  Completed: {section_count} sections extracted")
        except Exception as e:
            print(f"  Error processing {pdf_file.name}: {str(e)}")
            continue

    print(f"\nTotal sections extracted: {len(all_sections)}")
    if not all_sections:
        print("No sections extracted. Exiting.")
        return

    print("\nCalculating relevance scores...")
    ranked_sections = processor.calculate_relevance_scores_batch(all_sections, persona, job)

    top_k = 15
    print(f"\nExtracting top {top_k} subsections...")
    subsections = processor.extract_subsections(ranked_sections, top_k)

    # Prepare output
    output = {
        "metadata": {
            "input_documents": sorted(processed_documents),
            "persona": persona,
            "job_to_be_done": job,
            "processing_timestamp": datetime.now().isoformat()
        },
        "extracted_sections": [
            {
                "document": s["document"],
                "section_title": s["section_title"],
                "importance_rank": s["importance_rank"],
                "page_number": s["page_number"]
            }
            for s in ranked_sections[:top_k]
        ],
        "subsection_analysis": [
            {
                "document": s["document"],
                "refined_text": s["refined_text"],
                "page_number": s["page_number"]
            }
            for s in subsections
        ]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n=== Results ===")
    print(f"Results written to: {output_path.resolve()}")
    print(f"Documents processed: {len(processed_documents)}")
    print(f"Total sections: {len(all_sections)}")
    print(f"Top sections analyzed: {len(subsections)}")

    print(f"\nTop 10 most relevant sections:")
    for i, section in enumerate(ranked_sections[:10]):
        score = section.get('relevance_score', 0.0)
        print(f"{i+1:2d}. [{section['document']}] {section['section_title'][:60]}... (Score: {score:.3f})")

    print("\nProcessing completed successfully!")


# Replace the old main invocation:
if __name__ == "__main__":
    main()
