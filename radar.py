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
EMAIL_USER = "wmaps2@gmail.com"
PASSWORD_APP = os.getenv("PASSWORD_APP")
ARCHIVO_BD = "estado_mercado.json"
URL_TARGET = "https://listado.mercadolibre.cl/inmuebles/departamentos/arriendo/_DisplayType_M_FULL*BATHROOMS_3-5_item*location_lat:-33.44382939080379*-33.426030143753444,lon:-70.5837450239563*-70.5447349760437?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX"

def obtener_uf():
    try:
        r = requests.get("https://mindicador.cl/api/uf", timeout=5)
        return r.json()['serie'][0]['valor']
    except: return 40000.0

def extraer_precio_limpio(texto_raw, valor_uf):
    t = texto_raw.replace('\xa0', ' ').replace('\n', ' ')
    uf_m = re.search(r'UF\s*([\d\.,]+)', t, re.I)
    if uf_m:
        val = float(uf_m.group(1).replace('.', '').replace(',', '.'))
        return f"$ {int(val*valor_uf):,}".replace(",", "."), int(val*valor_uf)
    montos = re.findall(r'\$\s*([\d\.,]+)', t)
    if montos:
        vals = [int(re.sub(r'[^\d]', '', m)) for m in montos]
        return f"$ {max(vals):,}".replace(",", "."), max(vals)
    return "Cons.", 0

def enviar_mail(actuales, nuevos, es_diario):
    msg = MIMEMultipart('alternative')
    # Volvemos a la lógica de argumentos para el asunto
    tipo = "Diario" if es_diario else "Novedad"
    msg['Subject'] = f"Radar Busca-Casa 🏠: {len(nuevos)} Nuevas | {len(actuales)} Totales"
    msg['From'] = formataddr(("Radar Busca-Casa", EMAIL_USER))
    msg['To'] = EMAIL_USER
    
    html = f"<html><body style='font-family:Arial;'><h2>🏠 Reporte Radar Busca-Casa</h2>"
    
    # Solo mostramos tablas si hay datos
    if nuevos:
        html += "<h3>✨ Novedades</h3>" + str(nuevos) # Simplificado para el ejemplo
    if actuales:
        html += "<h3>📋 Inventario</h3>" # Aquí iría tu función generar_tabla_html
    
    html += "</body></html>"
    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(EMAIL_USER, PASSWORD_APP)
        s.send_message(msg)

def ejecutar():
    # USAMOS TU TRUCO PARA EL TEST
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
        print("📡 Página cargada. Esperando renderizado de mapa...")
        time.sleep(25) # Un poco más de tiempo para el servidor cloud
        
        # Scroll dinámico para despertar el JS de Meli
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(5)
        
        # Selector más robusto que abarque cualquier cambio de clase
        items = driver.find_elements(By.XPATH, "//li[contains(@class, 'ui-search-layout__item')]")
        if not items:
            items = driver.find_elements(By.CSS_SELECTOR, ".ui-search-result__wrapper")
            
        print(f"🔎 Items encontrados: {len(items)}")
        
        current_state = {}
        for item in items:
            try:
                link = item.find_element(By.TAG_NAME, "a").get_attribute("href").split("#")[0]
                raw = item.get_attribute("innerText")
                p_fmt, p_val = extraer_precio_limpio(raw, val_uf)
                
                current_state[link] = {
                    "titulo": raw.split("\n")[0].strip()[:50],
                    "precio": p_fmt,
                    "precio_raw": p_val
                }
            except: continue

        # Cargar estado previo
        if os.path.exists(ARCHIVO_BD):
            with open(ARCHIVO_BD, "r") as f: last = json.load(f)
        else: last = {}

        nuevos = {k: current_state[k] for k in (set(current_state.keys()) - set(last.keys()))}
        
        # Si estamos forzando el test (es_diario=True), siempre manda mail
        # Si no, solo si hay algo nuevo o es el reporte oficial
        if current_state:
            enviar_mail(current_state, nuevos, es_diario)
            print("📧 Mail enviado con datos reales.")
        else:
            print("⚠️ No se extrajeron datos. Revisa la captura en el log.")

        with open(ARCHIVO_BD, "w") as f: json.dump(current_state, f, indent=4)
            
    finally:
        driver.quit()

if __name__ == "__main__": ejecutar()
