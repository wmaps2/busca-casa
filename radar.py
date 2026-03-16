import smtplib, json, time, os, re, requests, sys, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- ⚙️ CONFIGURACIÓN ---
EMAIL_USER = "wmaps2@gmail.com"
PASSWORD_APP = os.getenv("PASSWORD_APP") # Se mantiene como Secret en GitHub
ARCHIVO_BD = "estado_mercado.json"

# 🔗 URL DEL GIST (Reemplaza con tu URL RAW del Gist)
URL_RAW_GIST = "https://gist.githubusercontent.com/wmaps2/a858b601b5eee5e74961903bd784352f/raw/ml_cookies.json"

# 🕒 HORA DEL REPORTE DIARIO FIJO
HORA_REPORTE_FIJO = 9 

URLS = {
    "🏢 DEPARTAMENTOS": "https://listado.mercadolibre.cl/inmuebles/departamentos/arriendo/_DisplayType_M_FULL*BATHROOMS_3-5_item*location_lat:-33.44382939080379*-33.426030143753444,lon:-70.5837450239563*-70.5447349760437?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX",
    "🏡 CASAS": "https://listado.mercadolibre.cl/inmuebles/casas/arriendo/_DisplayType_M_BEDROOMS_3-6_FULL*BATHROOMS_3-5?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX"
}

def obtener_uf():
    try:
        r = requests.get("https://mindicador.cl/api/uf", timeout=5)
        return r.json()['serie'][0]['valor']
    except: return 40000.0

def parsear_item(raw, valor_uf, item):
    t = raw.replace('\xa0', ' ').replace('\n', ' ')
    precio_fmt, precio_val = "Cons.", 0
    uf_m = re.search(r'UF\s*([\d\.,]+)', t, re.I)
    if uf_m:
        val = float(uf_m.group(1).replace('.', '').replace(',', '.'))
        precio_val = int(val * valor_uf)
        precio_fmt = f"$ {precio_val:,}".replace(",", ".") + f" (UF {val})"
    else:
        montos = re.findall(r'\$\s*([\d\.,]+)', t)
        if montos:
            vals = [int(re.sub(r'[^\d]', '', m)) for m in montos]
            precio_val = max(vals)
            precio_fmt = f"$ {precio_val:,}".replace(",", ".")

    m2 = f"{re.search(r'(\d+)\s*m²', t, re.I).group(1)} m²" if re.search(r'(\d+)\s*m²', t, re.I) else "--"
    dorm = f"{re.search(r'(\d+)\s*dorm', t, re.I).group(1)}D" if re.search(r'(\d+)\s*dorm', t, re.I) else "-"
    ban = f"{re.search(r'(\d+)\s*baño', t, re.I).group(1)}B" if re.search(r'(\d+)\s*baño', t, re.I) else "-"

    try:
        titulo = item.find_element(By.TAG_NAME, "h2").text
    except:
        titulo = "Propiedad en Vitacura"
    return titulo, precio_fmt, precio_val, m2, f"{dorm} / {ban}"

def generar_tabla_html(propiedades, titulo, color_bg, url_busqueda):
    if not propiedades: return ""
    props_ordenadas = dict(sorted(propiedades.items(), key=lambda x: x[1].get('precio_raw', 0)))
    html = f"<h4 style='color:{color_bg}; font-family:Arial; margin-bottom: 5px;'>{titulo}</h4>"
    html += '<table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:Arial; font-size:13px; text-align:center;">'
    html += f'<tr style="background:{color_bg}; color:white;"><th style="width:50%; text-align:left;">Propiedad (Link)</th><th style="width:10%;">m²</th><th style="width:15%;">Dorm/Bañ</th><th style="width:25%; text-align:right;">Arriendo Mensual</th></tr>'
    for link, info in props_ordenadas.items():
        html += f"<tr><td style='text-align:left;'><a href='{link}' style='color:#004a99; text-decoration:none;'><b>{info.get('titulo')}</b></a></td><td>{info.get('m2')}</td><td>{info.get('dorm_ban')}</td><td style='text-align:right;'><b>{info.get('precio')}</b></td></tr>"
    html += f"</table><div style='text-align:right; margin-top:8px; margin-bottom:15px;'><a href='{url_busqueda}' style='color:#004a99; font-family:Arial; font-size:12px; text-decoration:none;'><b>🔗 Link Búsqueda</b></a></div>"
    return html

def enviar_mail(actuales_dict, nuevos_dict, es_diario):
    msg = MIMEMultipart('alternative')
    hora_str = time.strftime("%H:%M")
    total_nuevas = sum(len(n) for n in nuevos_dict.values())
    total_actuales = sum(len(a) for a in actuales_dict.values())
    tipo = "Diario" if es_diario and total_nuevas == 0 else "Alerta"
    msg['Subject'] = f"Radar Busca-Casa 🏠 [{tipo} {hora_str}]: {total_nuevas} Nuevas | {total_actuales} Totales"
    msg['From'] = formataddr(("Radar Busca-Casa", EMAIL_USER))
    msg['To'] = EMAIL_USER
    html = f"<html><body style='font-family:Arial; padding:10px;'><h2>🏠 Reporte Radar Busca-Casa</h2><hr>"
    for categoria, url_busqueda in URLS.items():
        cat_nuevos, cat_actuales = nuevos_dict.get(categoria, {}), actuales_dict.get(categoria, {})
        if cat_actuales or cat_nuevos:
            html += f"
