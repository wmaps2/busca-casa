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

# --- 🗺️ PORTAFOLIO DE BÚSQUEDAS ---
URLS = {
    "🏢 DEPARTAMENTOS": "https://listado.mercadolibre.cl/inmuebles/departamentos/arriendo/_DisplayType_M_FULL*BATHROOMS_3-5_item*location_lat:-33.44382939080379*-33.426030143753444,lon:-70.5837450239563*-70.5447349760437?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX",
    "🏡 CASAS": "https://listado.mercadolibre.cl/inmuebles/casas/arriendo/_DisplayType_M_BEDROOMS_3-6_FULL*BATHROOMS_3-5?polygon_location=po%60kEzawmL%60Ik%40%7CEcAzWmAxDsL%60CiCpBcAlAwEtCmBFeb%40mA%7BD%7DCqCk%40%7DAsLsOmLiUqBeBwGcAyU%3FgA%60%40%5Bz%40gAbHq%40lX%3FzR%7E%40vQ%3Fxk%40zAdE%60Ah%40tEXfAa%40UX"
}

def obtener_uf():
    try:
        r = requests.get("https://mindicador.cl/api/uf", timeout=5)
        return r.json()['serie'][0]['valor']
    except: 
        return 40000.0

def parsear_item(raw, valor_uf, item):
    t = raw.replace('\xa0', ' ').replace('\n', ' ')

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

    m2_m = re.search(r'(\d+)\s*m²', t, re.I)
    m2 = f"{m2_m.group(1)} m²" if m2_m else "--"

    dorm_m = re.search(r'(\d+)\s*dorm', t, re.I)
    ban_m = re.search(r'(\d+)\s*baño', t, re.I)
    dorm = f"{dorm_m.group(1)}D" if dorm_m else "-"
    ban = f"{ban_m.group(1)}B" if ban_m else "-"

    try:
        titulo = item.find_element(By.TAG_NAME, "h2").text
        if not titulo: raise Exception()
    except:
        lineas = [l.strip() for l in raw.split("\n") if l.strip() and l.strip().upper() not in ["VISTO", "CONTACTADO", "PROMOCIONADO", "NUEVO", "RESERVADO"]]
        titulo = lineas[0][:60] if lineas else "Propiedad"

    return titulo, precio_fmt, precio_val, m2, f"{dorm} / {ban}"

def generar_tabla_html(propiedades, titulo, color_bg, url_busqueda):
    if not propiedades: return ""
    props_ordenadas = dict(sorted(propiedades.items(), key=lambda x: x[1].get('precio_raw', 0)))

    html = f"<h4 style='color:{color_bg}; font-family:Arial; margin-bottom: 5px;'>{titulo}</h4>"
    html += '<table border="1" cellpadding="10" cellspacing="0" style="border-collapse:collapse; width:100%; font-family:Arial; font-size:13px; text-align:center;">'
    html += f'<tr style="background:{color_bg}; color:white;"><th style="width:50%; text-align:left;">Propiedad (Link)</th><th style="width:10%;">m²</th><th style="width:15%;">Dorm/Bañ</th><th style="width:25%; text-align:right;">Arriendo Mensual</th></tr>'

    for link, info in props_ordenadas.items():
        html += f"""<tr>
            <td style="text-align:left;"><a href="{link}" style="color:#004a99; text-decoration:none;"><b>{info.get('titulo')}</b></a></td>
            <td>{info.get('m2')}</td>
            <td>{info.get('dorm_ban')}</td>
            <td style="text-align:right;"><b>{info.get('precio')}</b></td>
        </tr>"""

    # --- 🔗 LINK DE BÚSQUEDA AÑADIDO AL FINAL DE LA TABLA ---
    html += f"</table>"
    html += f"<div style='text-align:right; margin-top:8px; margin-bottom:15px;'><a href='{url_busqueda}' style='color:#004a99; font-family:Arial; font-size:12px; text-decoration:none;'><b>🔗 Link Búsqueda</b></a></div>"
    
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
        cat_nuevos = nuevos_dict.get(categoria, {})
        cat_actuales = actuales_dict.get(categoria, {})
        
        if cat_actuales or cat_nuevos:
            html += f"<h2 style='color:#333; margin-top:30px; border-bottom: 2px solid #ccc; padding-bottom: 5px;'>{categoria}</h2>"
            if cat_nuevos:
                html += generar_tabla_html(cat_nuevos, f"✨ NOVEDADES ({len(cat_nuevos)})", "#28a745", url_busqueda)
            if cat_actuales:
                html += generar_tabla_html(cat_actuales, f"📋 INVENTARIO COMPLETO ({len(cat_actuales)})", "#004a99", url_busqueda)
                
    html += "</body></html>"

    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(EMAIL_USER, PASSWORD_APP)
        s.send_message(msg)

def ejecutar():
    # TEST ACTIVADO: Forzamos el envío para ver las dos categorías y los links
    es_diario = True 
    print(f"🚀 Iniciando Radar Multi-Categoría (Cookies)... Modo Diario: {es_diario}")
    val_uf = obtener_uf()

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=2560,1440")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    try:
        # 1. INYECTAMOS LAS COOKIES PRIMERO (Base Domain)
        print("🍪 Inyectando sesión...")
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
                print("✅ Cookies cargadas.")
            except: 
                print("⚠️ Error leyendo las cookies JSON.")
        else:
            print("⚠️ No se encontraron cookies en el entorno.")

        current_state = {cat: {} for cat in URLS.keys()}

        # 2. 🔄 ITERAMOS SOBRE EL DICCIONARIO DE URLS
        for categoria, url in URLS.items():
            print(f"\n📡 Cargando {categoria}...")
            driver.get(url)

            wait = WebDriverWait(driver, 40)
            try: wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.ui-search-layout__item")))
            except: pass

            for _ in range(4):
                driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1.5)

            items_iniciales = driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item, .ui-search-result__wrapper")
            print(f"🔎 Items detectados en {categoria}: {len(items_iniciales)}")

            for i in range(len(items_iniciales)):
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

                    titulo, p_fmt, p_val, m2, dorm_ban = parsear_item(raw, val_uf, item)

                    current_state[categoria][link] = {
                        "titulo": titulo,
                        "precio": p_fmt,
                        "precio_raw": p_val,
                        "m2": m2,
                        "dorm_ban": dorm_ban
                    }
                except Exception:
                    continue

        # --- 🗃️ GESTIÓN DE ESTADO Y MIGRACIÓN ---
        if os.path.exists(ARCHIVO_BD):
            try:
                with open(ARCHIVO_BD, "r") as f: last = json.load(f)
                # Script de migración: Si el JSON viejo es plano, lo metemos dentro de Departamentos
                if last and "🏢 DEPARTAMENTOS" not in last and "🏡 CASAS" not in last:
                    last = {"🏢 DEPARTAMENTOS": last, "🏡 CASAS": {}}
            except:
                last = {cat: {} for cat in URLS.keys()}
        else: 
            last = {cat: {} for cat in URLS.keys()}

        nuevos = {cat: {} for cat in URLS.keys()}
        hay_novedades = False

        for categoria in URLS.keys():
            if categoria not in last: last[categoria] = {}
            
            nuevos[categoria] = {k: current_state[categoria][k] for k in (set(current_state[categoria].keys()) - set(last[categoria].keys()))}
            if nuevos[categoria]: hay_novedades = True

        total_procesados = sum(len(c) for c in current_state.values())
        print(f"\n📊 Procesamiento global listo. Totales en radar: {total_procesados}")

        if total_procesados > 0 and (hay_novedades or es_diario):
            enviar_mail(current_state, nuevos, es_diario)
            print("📧 Correo consolidado enviado con éxito.")
        else:
            print("😴 No hay novedades ni es hora del reporte. Guardando silencio.")

        with open(ARCHIVO_BD, "w") as f: json.dump(current_state, f, indent=4)

    finally:
        driver.quit()

if __name__ == "__main__": 
    ejecutar()
