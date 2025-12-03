import pdfplumber
import os
import re

def extract_decretos_by_specific_logic(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"El archivo {pdf_path} no existe.")
        return

    print(f"Procesando: {pdf_path}")
    
    all_lines = []
    
    # Paso 1: Leer todo el PDF y estructurar en líneas con su tamaño de fuente máximo
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=True, extra_attrs=['size'])
            if not words:
                continue
            
            # Filtrar pie de página (asumimos un margen inferior de 50 puntos)
            page_height = page.height
            FOOTER_MARGIN = 50
            words = [w for w in words if w['top'] < (page_height - FOOTER_MARGIN)]
            
            if not words:
                continue
            
            # Agrupar palabras en líneas
            current_line_words = [words[0]]
            for word in words[1:]:
                if abs(word['top'] - current_line_words[-1]['top']) < 3:
                    current_line_words.append(word)
                else:
                    text = " ".join([w['text'] for w in current_line_words])
                    sizes = [w['size'] for w in current_line_words]
                    max_size = max(sizes) if sizes else 0
                    all_lines.append({'text': text, 'size': max_size, 'page': page.page_number})
                    current_line_words = [word]
            
            if current_line_words:
                text = " ".join([w['text'] for w in current_line_words])
                sizes = [w['size'] for w in current_line_words]
                max_size = max(sizes) if sizes else 0
                all_lines.append({'text': text, 'size': max_size, 'page': page.page_number})

    # Paso 2: Encontrar el inicio de la Sección "DECRETOS" (Título Principal)
    # Buscamos la línea con "DECRETO" de mayor tamaño en todo el documento
    decreto_lines = [line for line in all_lines if "DECRETO" in line['text'].upper()]
    if not decreto_lines:
        print("No se encontró la palabra 'DECRETO' en el documento.")
        return

    main_title_size = max(line['size'] for line in decreto_lines)
    print(f"Tamaño de fuente del Título Principal de Sección DECRETOS: {main_title_size}")

    # Encontrar el índice de inicio (primera aparición del título principal)
    start_index = -1
    for i, line in enumerate(all_lines):
        if "DECRETO" in line['text'].upper() and abs(line['size'] - main_title_size) < 0.5:
            start_index = i
            break
    
    if start_index == -1:
        print("No se encontró el inicio de la sección.")
        return

    print(f"Inicio de Sección Principal detectado: '{all_lines[start_index]['text']}' (Pág {all_lines[start_index]['page']})")

    # Paso 3: Extraer el contenido de la Sección Principal
    # Va desde start_index hasta el próximo título del MISMO tamaño (o fin de archivo)
    section_lines = []
    for i in range(start_index + 1, len(all_lines)):
        line = all_lines[i]
        # Si encontramos otro título principal, cortamos
        if abs(line['size'] - main_title_size) < 0.5:
            print(f"Fin de Sección Principal detectado: '{line['text']}' (Pág {line['page']})")
            break
        section_lines.append(line)

    if not section_lines:
        print("La sección extraída está vacía.")
        return

    # Paso 4: Analizar los Decretos Individuales DENTRO de la sección
    # Buscamos el tamaño de fuente más grande dentro de esta sección (serán los subtítulos de cada decreto)
    # Ignoramos líneas vacías o muy cortas para evitar ruido
    valid_lines = [l for l in section_lines if len(l['text'].strip()) > 3]
    if not valid_lines:
        print("No hay contenido válido en la sección.")
        return

    # Buscamos el tamaño máximo dentro de la sección
    max_inner_size = max(l['size'] for l in valid_lines)
    print(f"Tamaño de fuente detectado para Decretos Individuales: {max_inner_size}")

    # Agrupar por Decretos Individuales
    individual_decrees = []
    current_decree_title = ""
    current_decree_content = []
    
    TOLERANCE = 0.5

    for line in section_lines:
        is_subtitle = abs(line['size'] - max_inner_size) < TOLERANCE
        
        # A veces el subtítulo ocupa varias líneas, o hay ruido. 
        # Asumimos que si tiene el tamaño maximo y contiene "DECRETO", es un inicio seguro.
        # O si el usuario dice "decreto XXXX/XXXX", buscamos ese patrón.
        # Pero seguiremos la regla de "letra más grande".
        
        if is_subtitle:
            # Si ya teníamos uno abierto, lo guardamos
            if current_decree_title:
                individual_decrees.append({
                    'titulo': current_decree_title,
                    'contenido': "\n".join(current_decree_content)
                })
            
            current_decree_title = line['text']
            current_decree_content = []
        else:
            if current_decree_title:
                current_decree_content.append(line['text'])
    
    # Guardar el último
    if current_decree_title:
        individual_decrees.append({
            'titulo': current_decree_title,
            'contenido': "\n".join(current_decree_content)
        })

    print(f"Se encontraron {len(individual_decrees)} decretos individuales dentro de la sección.")

    # Paso 5: Filtrar por palabras clave en Artículo 1
    role_keywords = ['juez', 'defensor', 'fiscal', 'asesor']
    action_keywords = ['renuncia', 'designa'] # designa atrapa designación, designar, desígnase
    
    found_count = 0
    
    print("\n--- Resultados del Análisis ---")
    for decree in individual_decrees:
        content = decree['contenido']
        
        # Buscar Artículo 1
        # Regex ajustado para evitar falsos positivos como "artículo 175"
        # Buscamos "ARTICULO 1" seguido de algo que NO sea un dígito (ej: °, ., o espacio)
        match_art1 = re.search(r'(ART[ÍI]CULO\s+1(?:[^\d].*?))(\nART[ÍI]CULO\s+2|$)', content, re.DOTALL | re.IGNORECASE)
        
        if match_art1:
            art1_text = match_art1.group(1).strip()
            # Normalizar espacios pero MANTENER mayúsculas/minúsculas originales
            art1_text_normalized = re.sub(r'\s+', ' ', art1_text)
            
            # Para el chequeo de palabras clave usamos minúsculas
            text_for_check = art1_text_normalized.lower()
            
            has_role = any(k in text_for_check for k in role_keywords)
            has_action = any(k in text_for_check for k in action_keywords)
            
            if has_role and has_action:
                found_count += 1
                # Remover el prefijo "artículo 1..." del texto ORIGINAL
                # Ajustamos regex para comer también puntos o guiones después del número
                content_only = re.sub(r'^art[íi]culo\s+1\s*[º°]?\s*[\.\-]?\s*', '', art1_text_normalized, flags=re.IGNORECASE).strip()
                
                # Capitalizar la primera letra (manteniendo el resto igual)
                if content_only:
                    content_only = content_only[0].upper() + content_only[1:]
                
                print(f"\n{decree['titulo']}")
                print(f"{content_only}")
                print("-" * 20)
    
    print(f"\nTotal de decretos relevantes encontrados: {found_count}")

if __name__ == "__main__":
    pdf_path = "OFICIAL (8).pdf"
    extract_decretos_by_specific_logic(pdf_path)
