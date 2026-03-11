import smtplib, json, time, os, re, requests, sys
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
PASSWORD_APP = os.getenv("PASSWORD_APP")
ARCHIVO_BD = "estado_mercado.json"
URL_TARGET = "https://listado.mercadolibre.cl/inmuebles/departamentos/arriendo/_DisplayType_M_FULL*BATHROOMS_3-5_item*location_lat:-33.44382939080379*-33.426030143753444,lon:-70.5837450239563*-70.5447349760437?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX"

def obtener_uf():
    try:
        r = requests.get("https://mindicador.cl/api/uf", timeout=5)
        return r.json()['serie'][0]['valor']
    except: 
        return 40000.0

# --- 🧮 CALCULADORA DE ANTIGÜEDAD ---
def calcular_antiguedad(texto):
    if not texto or texto == "--": return 9999
    t = texto.lower()
    
    if "hoy" in t: return 0
    if "ayer" in t: return 1
    
    numeros = re.findall(r'\d+', t)
    val = int(numeros[0]) if numeros else 1
    
    if "día" in t or "dia" in t: return val
    if "semana" in t: return val * 7
    if "mes" in t: return val * 30
    if "año" in t or "ano" in t: return val * 365
    
    return 9999

# --- 🧠 PARSER AVANZADO DE TEXTO ---
def parsear_item(raw, valor_uf, item):
    t = raw.replace('\xa0', ' ').replace('\n', ' ')

    # 1. Extraer Precio
    precio_fmt = "Cons."
    precio_val = 0
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

    # 2. Extraer Metros Cuadrados
    m2_m = re.search(r'(\d+)\s*m²', t, re.I)
    m2 = f"{m2_m.group(1)} m²" if m2_m else "--"

    # 3. Extraer Dormitorios y Baños
    dorm_m = re.search(r'(\d+)\s*dorm', t, re.I)
    ban_m = re.search(r'(\d+)\s*baño', t, re.I)
    dorm = f"{dorm_m.group(1)}D" if dorm_m else "-"
    ban = f"{ban_m.group(1)}B" if ban_m else "-"

    # 4. Extraer Fecha de Publicación y Edad Numérica
    publicado = "--"
    for linea in raw.split('\n'):
        if "publicado" in linea.lower():
            publicado = linea.strip()
            break
            
    dias = calcular_antiguedad(publicado)

    # 5. Extraer Título
    try:
        titulo = item.find_element(By.TAG_NAME, "h2").text
        if not titulo: raise Exception()
    except:
        lineas = [l.strip() for l in raw.split("\n") if l.strip() and l.strip().upper() not in ["VISTO", "CONTACTADO", "PROMOCIONADO", "NUEVO", "RESERVADO"] and "PUBLICADO" not in l.strip().upper()]
        titulo = lineas[0][:60] if lineas else "Propiedad"

    return titulo, precio_fmt, precio_val, m2, f"{dorm} / {ban}", publicado, dias

# --- 🎨 DISEÑO HTML Y ORDENAMIENTO ---
def generar_tabla_html(propiedades, titulo, color_bg, nuevos_links=None):
    if not propiedades: return ""
    
    # 🛠️ ORDENAMIENTO: Primero por días de antigüedad, si hay empate, por precio.
    props_ordenadas = dict(sorted(propiedades.items(), key=lambda x: (x[1].get('dias', 9999), x[1].get('precio_raw', 0))))

    html = f"<h3 style='color:{color_bg}; font-family:Arial;'>{titulo}</h3>"
    html += '<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:Arial; font-size:12px; text-align:center;">'
    html += f'<tr style="background:{color_bg}; color:white;"><th style="width:8%;">Estado</th><th style="width:30%; text-align:left;">Propiedad (Link)</th><th style="width:8%;">m²</th><th style="width:12%;">Dorm/Bañ</th><th style="width:17%;">Publicación</th><th style="width:25%; text-align:right;">Arriendo Mensual</th></tr>'

    for link, info in props_ordenadas.items():
        es_nuevo = link in (nuevos_links or set())
        tag = '<span style="color:#28a745;"><b>✨ NUEVO</b></span>' if es_nuevo else '<span style="color:#6c757d;">Stock</span>'

        html += f"""<tr>
            <td>{tag}</td>
            <td style="text-align:left;"><a href="{link}" style="color:#004a99; text-decoration:none;"><b>{info.get('titulo')}</b></a></td>
            <td>{info.get('m2')}</td>
            <td>{info.get('dorm_ban')}</td>
            <td style="color:#555;"><i>{info.get('publicado')}</i></td>
            <td style="text-align:right;"><b>{info.get('precio')}</b></td>
        </tr>"""

    return html + "</table><br>"

def enviar_mail(actuales, nuevos, es_diario):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Radar Busca-Casa 🏠: {len(nuevos)} Nuevas | {len(actuales)} Totales"
    msg['From'] = formataddr(("Radar Busca-Casa", EMAIL_USER))
    msg['To'] = EMAIL_USER

    html = f"<html><body style='font-family:Arial; padding:10px;'><h2>🏠 Reporte Radar Busca-Casa</h2><hr>"
    if nuevos:
        html += generar_tabla_html(nuevos, "✨ NOVEDADES RECIENTES", "#28a745", set(nuevos.keys()))
    html += generar_tabla_html(actuales, "📋 INVENTARIO COMPLETO (Por más reciente)", "#004a99", set(nuevos.keys()))
    html += "</body></html>"

    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(EMAIL_USER, PASSWORD_APP)
        s.send_message(msg)

def ejecutar():
    es_diario = True # Mantén esto en True para tu prueba manual, luego cámbialo a: "--daily" in sys.argv
    val_uf = obtener_uf()

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=2560,1440")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    try:
        driver.get("https://www.mercadolibre.cl")
        time.sleep(3)

        cookies_raw = os.getenv("MY_COOKIES")
        if cookies_raw:
            try:
                for cookie in json.loads(cookies_raw):
                    cookie.pop('sameSite', None)
                    cookie.pop('storeId', None)
                    try: driver.add_cookie(cookie)
                    except: pass
            except: pass

        driver.get(URL_TARGET)

        wait = WebDriverWait(driver, 40)
        try: wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.ui-search-layout__item")))
        except: pass

        for _ in range(4):
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(1.5)

        items_iniciales = driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item, .ui-search-result__wrapper")
        num_items = len(items_iniciales)

        current_state = {}
        for i in range(num_items):
            try:
                lista_actualizada = driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item, .ui-search-result__wrapper")
                if i >= len(lista_actualizada): break
                item = lista_actualizada[i]

                links = item.find_elements(By.TAG_NAME, "a")
                if not links: continue
                link = None
                for a in links:
                    href = a.get_attribute("href")
                    if href and ("mercadolibre.cl" in href or "mlc" in href):
                        link = href.split("#")[0]
                        break
                if not link: continue

                raw = item.get_attribute("innerText")
                if not raw or raw.strip() == "":
                    raw = item.get_attribute("textContent")

                titulo, p_fmt, p_val, m2, dorm_ban, publicado, dias = parsear_item(raw, val_uf, item)

                current_state[link] = {
                    "titulo": titulo,
                    "precio": p_fmt,
                    "precio_raw": p_val,
                    "m2": m2,
                    "dorm_ban": dorm_ban,
                    "publicado": publicado,
                    "dias": dias # <--- Guardamos la edad en días para que la tabla pueda ordenar
                }
            except Exception:
                continue

        if os.path.exists(ARCHIVO_BD):
            with open(ARCHIVO_BD, "r") as f: last = json.load(f)
        else: last = {}

        nuevos = {k: current_state[k] for k in (set(current_state.keys()) - set(last.keys()))}

        if current_state:
            enviar_mail(current_state, nuevos, es_diario)

        with open(ARCHIVO_BD, "w") as f: json.dump(current_state, f, indent=4)

    finally:
        driver.quit()

if __name__ == "__main__": 
    ejecutar()
