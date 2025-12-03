import os
import requests
from bs4 import BeautifulSoup
import pdfplumber
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

def get_argentina_time():
    # Argentina es UTC-3
    return datetime.now(timezone.utc) - timedelta(hours=3)

def get_latest_bulletin_url():
    base_url = "https://boletinoficial.gba.gob.ar"
# ... (rest of file)


    url = f"{base_url}/ediciones-anteriores"
    response = requests.get(url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    links = soup.find_all('a', string=lambda text: text and "OFICIAL" in text)
    
    for link in links:
        href = link.get('href')
        if href and "/secciones/" in href and "/ver" in href:
            return f"{base_url}{href}" if href.startswith("/") else href
            
    return None

def extract_decrees(pdf_content):
    print("Iniciando extracción con pdfplumber...")
    
    all_lines = []
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
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
    except Exception as e:
        print(f"Error al procesar PDF: {e}")
        return []

    # Paso 2: Encontrar el inicio de la Sección "DECRETOS"
    decreto_lines = [line for line in all_lines if "DECRETO" in line['text'].upper()]
    if not decreto_lines:
        print("No se encontró la palabra 'DECRETO' en el documento.")
        return []

    main_title_size = max(line['size'] for line in decreto_lines)
    
    start_index = -1
    for i, line in enumerate(all_lines):
        if "DECRETO" in line['text'].upper() and abs(line['size'] - main_title_size) < 0.5:
            start_index = i
            break
    
    if start_index == -1:
        return []

    # Paso 3: Extraer el contenido de la Sección Principal
    section_lines = []
    for i in range(start_index + 1, len(all_lines)):
        line = all_lines[i]
        if abs(line['size'] - main_title_size) < 0.5:
            break
        section_lines.append(line)

    if not section_lines:
        return []

    # Paso 4: Analizar los Decretos Individuales
    valid_lines = [l for l in section_lines if len(l['text'].strip()) > 3]
    if not valid_lines:
        return []

    max_inner_size = max(l['size'] for l in valid_lines)
    
    individual_decrees = []
    current_decree_title = ""
    current_decree_content = []
    
    TOLERANCE = 0.5

    for line in section_lines:
        is_subtitle = abs(line['size'] - max_inner_size) < TOLERANCE
        
        if is_subtitle:
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
    
    if current_decree_title:
        individual_decrees.append({
            'titulo': current_decree_title,
            'contenido': "\n".join(current_decree_content)
        })

    # Paso 5: Filtrar y formatear
    role_keywords = ['juez', 'jueza', 'defensor', 'fiscal', 'asesor']
    action_keywords = ['renuncia', 'designa']
    
    results = []
    
    for decree in individual_decrees:
        content = decree['contenido']
        
        match_art1 = re.search(r'(ART[ÍI]CULO\s+1(?:[^\d].*?))(\nART[ÍI]CULO\s+2|$)', content, re.DOTALL | re.IGNORECASE)
        
        if match_art1:
            art1_text = match_art1.group(1).strip()
            art1_text_normalized = re.sub(r'\s+', ' ', art1_text)
            text_for_check = art1_text_normalized.lower()
            
            has_role = any(k in text_for_check for k in role_keywords)
            has_action = any(k in text_for_check for k in action_keywords)
            
            if has_role and has_action:
                # Determinar tipo
                tipo = "Designación" if "designa" in text_for_check else "Renuncia"
                
                # Limpiar texto
                content_only = re.sub(r'^art[íi]culo\s+1\s*[º°]?\s*[\.\-]?\s*', '', art1_text_normalized, flags=re.IGNORECASE).strip()
                if content_only:
                    content_only = content_only[0].upper() + content_only[1:]
                
                results.append({
                    'titulo': decree['titulo'],
                    'texto': content_only,
                    'tipo': tipo
                })
                
    return results

def send_email(decrees):
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    email_to = os.environ.get('EMAIL_TO')
    
    if not email_user or not email_password or not email_to:
        print("Skipping email: Credentials not found.")
        return

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_to
    msg['Subject'] = f"Novedades Judiciales Boletín Oficial - {get_argentina_time().strftime('%Y-%m-%d')}"

    if not decrees:
        html_content = "<p>No hubo renuncias o designaciones en el Poder Judicial en el Boletín Oficial de hoy.</p>"
    else:
        # Contar tipos
        renuncias = sum(1 for d in decrees if d['tipo'] == 'Renuncia')
        designaciones = sum(1 for d in decrees if d['tipo'] == 'Designación')
        
        # Usamos HTML para dar formato (negrita y tamaño más grande)
        html_content = f"""
        <html>
        <body>
            <h2 style="font-weight: bold;">Cantidad de renuncias: {renuncias} | Cantidad de designaciones: {designaciones}</h2>
            <br>
        """
        
        for d in decrees:
            # Convertir saltos de línea a <br> si fuera necesario, aunque el texto ya viene limpio
            html_content += f"""
            <p>
                <strong>{d['titulo']}</strong><br>
                {d['texto']}
            </p>
            <hr>
            """
        
        html_content += """
        </body>
        </html>
        """

    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_password)
        text = msg.as_string()
        server.sendmail(email_user, email_to, text)
        server.quit()
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_no_update_email():
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    email_to = os.environ.get('EMAIL_TO')
    
    if not email_user or not email_password or not email_to:
        print("Skipping email: Credentials not found.")
        return

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_to
    msg['Subject'] = f"Estado Boletín Oficial - {get_argentina_time().strftime('%Y-%m-%d %H:%M')}"

    body = f"No se subió un nuevo Boletín Oficial a la fecha y hora: {get_argentina_time().strftime('%d/%m/%Y %H:%M')}."
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, email_to, msg.as_string())
        server.quit()
        print("Email de 'sin novedades' enviado correctamente.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    print("Buscando el último boletín oficial...")
    section_url = get_latest_bulletin_url()
    
    if not section_url:
        print("No se encontró el enlace a la sección OFICIAL.")
        return
        
    print(f"Enlace encontrado: {section_url}")
    
    try:
        section_id = section_url.split("/secciones/")[1].split("/")[0]
        pdf_url = f"https://boletinoficial.gba.gob.ar/secciones/{section_id}/descargar"
    except IndexError:
        print("No se pudo extraer el ID de la sección.")
        return

    # --- Lógica de Estado (Persistencia) ---
    state_file = "last_processed_id.txt"
    last_id = ""
    
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            last_id = f.read().strip()
    
    if section_id == last_id:
        print(f"El boletín {section_id} ya fue procesado anteriormente.")
        print("Enviando email de aviso...")
        send_no_update_email()
        return
    else:
        print(f"Nuevo boletín detectado: {section_id} (Anterior: {last_id})")
    # ---------------------------------------

    print(f"Descargando PDF de: {pdf_url}")
    response = requests.get(pdf_url)
    response.raise_for_status()
    
    print("Extrayendo decretos...")
    decrees = extract_decrees(response.content)
    
    print(f"Se encontraron {len(decrees)} decretos relevantes.")
    for d in decrees:
        print(f"[{d['tipo']}] {d['titulo']}")
    
    print("Enviando email...")
    send_email(decrees)
    
    # Actualizar el archivo de estado solo si todo salió bien
    with open(state_file, "w") as f:
        f.write(section_id)
    print(f"Estado actualizado: {section_id}")

if __name__ == "__main__":
    main()
