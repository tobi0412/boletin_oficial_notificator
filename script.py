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

def extract_page_3(pdf_content):
    pdf_file = io.BytesIO(pdf_content)
    reader = PyPDF2.PdfReader(pdf_file)
    
    if len(reader.pages) < 3:
        return "El PDF tiene menos de 3 páginas."
        
    page = reader.pages[2] 
    text = page.extract_text()
    return text

def send_email(content, pdf_content=None):
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    email_to = os.environ.get('EMAIL_TO')
    
    if not email_user or not email_password or not email_to:
        print("Skipping email: Credentials not found.")
        return

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = email_to
    msg['Subject'] = f"Boletín Oficial - Página 3 - {datetime.now().strftime('%Y-%m-%d')}"

    body = f"Contenido de la página 3:\n\n{content}"
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
    
    print("Extrayendo contenido de la página 3...")
    text = extract_page_3(response.content)
    print("Contenido extraído:")
    print(text[:500] + "...") 
    
    print("Enviando email...")
    send_email(text)

if __name__ == "__main__":
    main()
