import os
from pypdf import PdfWriter

def merge_pdfs(pdf_paths, output_path):
    """
    Merge multiple PDFs into a single PDF.
    pdf_paths: list of paths to PDF files to merge
    output_path: path for the merged PDF
    """
    try:
        writer = PdfWriter()
        
        for pdf_path in pdf_paths:
            try:
                from pypdf import PdfReader
                reader = PdfReader(pdf_path)
                for page in reader.pages:
                    writer.add_page(page)
            except Exception as e:
                raise Exception(f"Error reading {pdf_path}: {e}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        with open(output_path, "wb") as output_file:
            writer.write(output_file)
        
        return True
    except Exception as e:
        raise Exception(f"Error merging PDFs: {e}")
