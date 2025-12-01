import os
import requests
from bs4 import BeautifulSoup
import PyPDF2
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def get_latest_bulletin_url():
    base_url = "https://boletinoficial.gba.gob.ar"
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

def get_pdf_url(section_url):
    response = requests.get(section_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    
    links = soup.find_all('a')
    for link in links:
        href = link.get('href')
        if href and (".pdf" in href or "descargar" in href.lower()):
             
             return f"https://boletinoficial.gba.gob.ar{href}" if href.startswith("/") else href
             
    return None

import re

def extract_appointments(pdf_content):
    pdf_file = io.BytesIO(pdf_content)
    reader = PyPDF2.PdfReader(pdf_file)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    # Normalize text
    normalized_text = re.sub(r'\s+', ' ', full_text)

    # Split by Decree
    decrees = re.split(r'(DECRETO N°\s*[\d/]+)', normalized_text)
    
    results = []
    
    for i in range(1, len(decrees), 2):
        if i+1 >= len(decrees): break
        decree_num = decrees[i].replace("DECRETO N°", "").strip()
        content = decrees[i+1]
        
        # Stricter Regex for Appointments
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

def send_email(appointments):
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    email_to = os.environ.get('EMAIL_TO')
    
    if not email_user or not email_password or not email_to:
        print("Skipping email: Credentials not found.")
        return

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_to
    msg['Subject'] = f"Nombramientos Boletín Oficial - {datetime.now().strftime('%Y-%m-%d')}"

    if not appointments:
        body = "No se encontraron nombramientos en el Boletín Oficial de hoy."
    else:
        body = "Se encontraron los siguientes nombramientos:\n\n"
        for app in appointments:
            body += f"- Decreto {app['decree']}: Designación de {app['name']} como {app['position']}\n"

    msg.attach(MIMEText(body, 'plain'))
    
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

    print(f"Descargando PDF de: {pdf_url}")
    response = requests.get(pdf_url)
    response.raise_for_status()
    
    print("Extrayendo nombramientos...")
    appointments = extract_appointments(response.content)
    
    print(f"Se encontraron {len(appointments)} nombramientos.")
    for app in appointments:
        print(f"- Decreto {app['decree']}: Designación de {app['name']} como {app['position']}")
    
    print("Enviando email...")
    send_email(appointments)

if __name__ == "__main__":
    main()
