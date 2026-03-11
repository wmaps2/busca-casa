def ejecutar():
    es_diario = True # Forzado para el test
    val_uf = obtener_uf()
    
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    
    # --- CAMUFLAJE DE BOT ---
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    
    # Engañar al navegador para que diga que no es un bot
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
      "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    try:
        print(f"📡 Apuntando a: {URL_TARGET[:60]}...")
        driver.get(URL_TARGET)
        
        # Espera dinámica: damos tiempo a que el JS pinte los departamentos
        time.sleep(30) 
        
        # Scroll por etapas para simular lectura humana
        for i in range(3):
            driver.execute_script(f"window.scrollBy(0, {400 * (i+1)});")
            time.sleep(2)

        # Intentamos capturar los items con varios selectores posibles
        items = driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item")
        if not items:
            items = driver.find_elements(By.CLASS_NAME, "ui-search-result__wrapper")
        if not items:
            # Si aún no hay nada, buscamos cualquier link que parezca propiedad
            items = driver.find_elements(By.XPATH, "//a[contains(@href, 'articulo.mercadolibre.cl/MLC')]")

        print(f"🔎 Items detectados en el DOM: {len(items)}")
        
        current_state = {}
        # ... (el resto del código de extracción se mantiene igual)
