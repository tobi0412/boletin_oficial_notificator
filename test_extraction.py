import PyPDF2
import re

def extract_appointments_from_pdf(pdf_path):
    reader = PyPDF2.PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    # Normalize text to handle line breaks within sentences
    # This is crucial because PDF extraction often breaks lines in the middle of sentences.
    # We'll replace newlines with spaces, but keep double newlines as paragraph breaks if possible.
    # For regex, it's often easier to just work with a single long string and handle whitespace in the regex.
    normalized_text = re.sub(r'\s+', ' ', full_text)

    # Regex to find decrees
    # Pattern: DECRETO N° [Number] ... Designar [Position] ... al/a la [Name] ...
    # We need to be careful not to capture too much.
    
    # Strategy:
    # 1. Find all "DECRETO N° X/Y" blocks.
    # 2. Inside each block, look for "Designar".
    
    # Let's try a regex that captures the Decree Number and the designation text.
    # Note: "Designar" might be "Designar en el cargo de..." or just "Designar..."
    
    # Example from user image:
    # DECRETO N° 1651/2025
    # ...
    # ARTÍCULO 1°. Designar JUEZ de TRIBUNAL DEL TRABAJO N° 5 ... al doctor Luis Oscar ROMASZCZUK ...
    
    # Regex breakdown:
    # DECRETO N°\s*([\d/]+)  -> Capture Decree Number
    # .*?                    -> Skip text until Article 1
    # ARTÍCULO 1°.*?Designar\s+(.*?) -> Capture Position (non-greedy)
    # \s+al\s+(?:doctor|señor|doctora|señora)\s+(.*?) -> Capture Name (non-greedy)
    # \s*\(DNI               -> Stop at DNI
    
    pattern = re.compile(
        r'DECRETO N°\s*([\d/]+).*?ARTÍCULO 1°.*?Designar\s+(.*?)\s+al\s+(?:doctor|señor|doctora|señora|dr\.|dra\.|sr\.|sra\.)\s+(.*?)\s*\(DNI',
        re.IGNORECASE | re.DOTALL
    )
    
    # Debug: Print first 2000 chars of normalized text to see what we are dealing with
    # print("DEBUG: Normalized Text Start:")
    # print(normalized_text[:2000])
    # print("DEBUG: Normalized Text End")
    
    decrees = re.split(r'(DECRETO N°\s*[\d/]+)', normalized_text)
    
    # print(f"DEBUG: Found {len(decrees)} segments after split.")
    
    results = []
    
    for i in range(1, len(decrees), 2):
        if i+1 >= len(decrees): break
        decree_num = decrees[i].replace("DECRETO N°", "").strip()
        content = decrees[i+1]
        
        # Stricter Regex for Appointments
        # We want to capture:
        # 1. Position (between "Designar" and "al")
        # 2. Name (between "al [Title]" and "(DNI")
        
        # Note: The text might have extra spaces or newlines normalized to spaces.
        # We use non-greedy matching .*? but ensure we anchor to "ARTÍCULO 1°"
        
        designation_match = re.search(
            r'ARTÍCULO 1°.*?Designar\s+(.*?)\s+al\s+(?:doctor|señor|doctora|señora|dr\.|dra\.|sr\.|sra\.)\s+(.*?)\s*\(DNI',
            content,
            re.IGNORECASE
        )
        
        if designation_match:
            position = designation_match.group(1).strip()
            name = designation_match.group(2).strip()
            
            # Filter out if the match is too long (likely a false positive or bad extraction)
            if len(position) > 200 or len(name) > 100:
                continue
                
            results.append({
                'decree': decree_num,
                'position': position,
                'name': name
            })
            
    return results

if __name__ == "__main__":
    pdf_path = "OFICIAL (6).pdf"
    appointments = extract_appointments_from_pdf(pdf_path)
    
    print(f"Se encontraron {len(appointments)} nombramientos:")
    for app in appointments:
        print(f"- Decreto {app['decree']}: Designación de {app['name']} como {app['position']}")
