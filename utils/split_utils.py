import os
from pypdf import PdfReader, PdfWriter

def split_pdf_by_pages(input_path, output_dir, page_ranges):
    """
    Split PDF by custom page ranges.
    page_ranges: list of tuples [(start1, end1), (start2, end2), ...]
                 page numbers are 1-indexed for user input.
    """
    try:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Read the PDF
        reader = PdfReader(input_path)
        total_pages = len(reader.pages)
        
        # Validate page ranges
        for start, end in page_ranges:
            if start < 1 or end > total_pages or start > end:
                raise ValueError(f"Invalid page range: {start}-{end}. PDF has {total_pages} pages.")
        
        output_files = []
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        for i, (start, end) in enumerate(page_ranges):
            writer = PdfWriter()
            # Convert 1-indexed to 0-indexed
            for page_num in range(start - 1, end):
                writer.add_page(reader.pages[page_num])
            
            # Create output filename
            if start == end:
                output_filename = f"{base_name}_page_{start}.pdf"
            else:
                output_filename = f"{base_name}_pages_{start}_to_{end}.pdf"
            output_path = os.path.join(output_dir, output_filename)
            
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            output_files.append(output_path)
        
        return output_files
    except Exception as e:
        raise Exception(f"Error splitting PDF by pages: {e}")

def split_pdf_equal_parts(input_path, output_dir, num_parts):
    """
    Split PDF into equal parts.
    num_parts: number of parts to split into.
    """
    try:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Read the PDF
        reader = PdfReader(input_path)
        total_pages = len(reader.pages)
        
        if num_parts < 1 or num_parts > total_pages:
            raise ValueError(f"Number of parts ({num_parts}) must be between 1 and total pages ({total_pages}).")
        
        # Calculate pages per part
        pages_per_part = total_pages // num_parts
        remainder = total_pages % num_parts
        
        output_files = []
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        current_page = 0
        
        for part in range(num_parts):
            # Calculate pages for this part
            extra_page = 1 if part < remainder else 0
            part_pages = pages_per_part + extra_page
            
            if part_pages == 0:
                continue
                
            start_page = current_page + 1
            end_page = current_page + part_pages
            
            writer = PdfWriter()
            for page_num in range(current_page, current_page + part_pages):
                writer.add_page(reader.pages[page_num])
            
            # Create output filename
            output_filename = f"{base_name}_part_{part+1}_of_{num_parts}.pdf"
            output_path = os.path.join(output_dir, output_filename)
            
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            output_files.append(output_path)
            
            current_page += part_pages
        
        return output_files
    except Exception as e:
        raise Exception(f"Error splitting PDF into equal parts: {e}")
