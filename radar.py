import smtplib, json, time, os, re, requests, sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- ⚙️ CONFIGURACIÓN ---
EMAIL_USER = "wmaps2@gmail.com"  # Tu mail directo
PASSWORD_APP = os.getenv("PASSWORD_APP") # La clave sigue protegida en Secrets
ARCHIVO_BD = "estado_mercado.json"
URL_TARGET = "https://listado.mercadolibre.cl/inmuebles/departamentos/arriendo/_DisplayType_M_FULL*BATHROOMS_3-5_item*location_lat:-33.44382939080379*-33.426030143753444,lon:-70.5837450239563*-70.5447349760437?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX"

def obtener_uf():
    try:
        r = requests.get("https://mindicador.cl/api/uf", timeout=5)
        return r.json()['serie'][0]['valor']
    except: return 40000.0

def extraer_precio_limpio(texto_raw, valor_uf):
    t = texto_raw.replace('\xa0', ' ').replace('\n', ' ')
    uf_match = re.search(r'UF\s*([\d\.,]+)', t, re.I)
    if uf_match:
        val_uf = float(uf_match.group(1).replace('.', '').replace(',', '.'))
        total_clp = int(val_uf * valor_uf)
        return f"$ {total_clp:,} (UF {val_uf})".replace(",", "."), total_clp
    montos = re.findall(r'\$\s*([\d\.,]+)', t)
    if montos:
        valores = [int(re.sub(r'[^\d]', '', m)) for m in montos]
        return f"$ {max(valores):,}".replace(",", "."), max(valores)
    return "Consultar", 0

def generar_tabla_html(propiedades, titulo, color, nuevos_links=None):
    if not propiedades: return ""
    props_ordenadas = dict(sorted(propiedades.items(), key=lambda x: x[1].get('precio_raw', 0)))
    html = f"<h3 style='color:{color}; font-family:Arial;'>{titulo}</h3>"
    html += '<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:Arial; font-size:12px;">'
    html += f'<tr style="background:{color}; color:white;"><th>Estado</th><th>Propiedad</th><th>m²</th><th>D/B</th><th>Precio</th></tr>'
    for link, info in props_ordenadas.items():
        es_nuevo = link in (nuevos_links or set())
        tag = '<b>[NUEVO]</b>' if es_nuevo else 'Stock'
        html += f"""<tr><td>{tag}</td><td><a href="{link}">{info.get('titulo')}</a></td>
            <td>{info.get('m2')}m²</td><td>{info.get('piezas')}D/{info.get('baños')}B</td><td>{info.get('precio')}</td></tr>"""
    return html.replace(",", ".") + "</table><br>"

def enviar_mail(actuales, nuevos, es_diario):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Radar Busca-Casa 🏠: {len(nuevos)} Nuevas | {len(actuales)} Totales"
    msg['From'] = formataddr(("Radar Busca-Casa", EMAIL_USER))
    msg['To'] = EMAIL_USER
    html = f"<html><body><h2>🏠 Radar Busca-Casa</h2>"
    if nuevos: html += generar_tabla_html(nuevos, "✨ NOVEDADES", "#28a745", set(nuevos.keys()))
    html += generar_tabla_html(actuales, "📋 INVENTARIO COMPLETO", "#004a99", set(nuevos.keys()))
    html += "</body></html>"
    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(EMAIL_USER, PASSWORD_APP)
        s.send_message(msg)

def ejecutar():
    # es_diario = "--daily" in sys.argv
    es_diario = True
    val_uf = obtener_uf()
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    
    try:
        driver.get(URL_TARGET)
        time.sleep(20)
        items = driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item, .ui-search-result__wrapper")
        current_state = {}
        for item in items:
            try:
                link = item.find_element(By.TAG_NAME, "a").get_attribute("href").split("#")[0]
                raw = item.get_attribute("innerText")
                p_fmt, p_val = extraer_precio_limpio(raw, val_uf)
                m2_m = re.search(r'([\d\.,]+)\s*m²', raw)
                d = re.search(r'(\d+)\s*(?:dorm|pieza)', raw, re.I)
                b = re.search(r'(\d+)\s*(?:baño)', raw, re.I)
                current_state[link] = {
                    "titulo": raw.split("\n")[0].strip()[:50], "precio": p_fmt, "precio_raw": p_val,
                    "m2": int(re.sub(r'[^\d]', '', m2_m.group(1))) if m2_m else "N/A",
                    "piezas": d.group(1) if d else "?", "baños": b.group(1) if b else "?"
                }
            except: continue

        if os.path.exists(ARCHIVO_BD):
            with open(ARCHIVO_BD, "r") as f: last = json.load(f)
        else: last = {}

        nuevos = {k: current_state[k] for k in (set(current_state.keys()) - set(last.keys()))}
        
        if nuevos or es_diario:
            enviar_mail(current_state, nuevos, es_diario)
            print("📧 Mail enviado.")
        
        with open(ARCHIVO_BD, "w") as f: json.dump(current_state, f, indent=4)
    finally: driver.quit()


if __name__ == "__main__": ejecutar()
