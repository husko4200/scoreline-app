# 📈 CONTEXTO GENERAL DEL PROYECTO: ANÁLISIS DEPORTIVO

> **Documento de Contexto y Arquitectura Integral**
> Diseñado para que cualquier desarrollador o Inteligencia Artificial (IA) entienda el 100% de la aplicación, su arquitectura, lógica de negocio, modelos matemáticos y estructura de archivos sin necesidad de inspeccionar el código fuente completo.

---

## 1. Resumen Ejecutivo de la Aplicación

**Análisis Deportivo** es una aplicación web analítica de alto rendimiento desarrollada en **Python** con **Streamlit**. Está enfocada en el análisis estadístico avanzado, seguimiento de marcadores en tiempo real y análisis probabilístico orientado a mercados de apuestas deportivas (líneas de *Over/Under*, *Hándicaps*, *Moneyline*, *Both Teams to Score*, utilidades de jugadores y parlays/combinadas).

### Deportes Cubiertos:
1. **🏀 NBA (Baloncesto):** Marcador en vivo, seguimiento de líneas de equipo/jugadores, rotaciones, reporte de bajas, simulación Monte Carlo de partidos/jugadores y lector visual de boletas de apuestas combinadas (OCR con Claude Vision).
2. **⚽ Fútbol (Soccer):** Cobertura de más de 20 ligas europeas y americanas más selecciones nacionales. Modelo predictivo Poisson, seguimiento de tiros, córners, tarjetas, faltas, análisis de árbitros y cuotas de mercado (Pinnacle, Bet365) sin margen (*fair odds*).
3. **🎾 Tenis:** Análisis de líneas de jugadores en circuitos ATP y WTA (games, sets, tie-breaks, hándicaps, desgaste físico y perfil por superficie).

---

## 2. Stack Tecnológico y Dependencias

| Componente | Tecnología | Propósito |
| :--- | :--- | :--- |
| **Framework Web** | `Streamlit >= 1.37` | Interfaz reactiva, fragmentos de actualización parcial (`st.fragment`), controles y componentes. |
| **Procesamiento de Datos** | `pandas >= 2.0`, `numpy` | Limpieza, series de tiempo, transformaciones matriciales y agrupaciones. |
| **Visualización** | `altair >= 5` | Gráficos interactivos de líneas, barras y medias móviles. |
| **Generación Gráfica** | `Pillow (PIL)` | Exportación de tarjetas resumen en imágenes PNG de alta resolución (1080x1500) para redes sociales. |
| **Redes y Peticiones** | `requests` (Session unificada) | Conexión HTTP con reintentos y backoff exponencial a APIs públicas y repositorios de datos. |
| **Inteligencia Artificial / Visión** | `anthropic` (opcional en `nba_combinada.py`) | Extracción OCR estructurada de boletas de apuestas combinadas mediante Claude Sonnet. |
| **Reconocimiento de Voz** | Web Speech API (HTML5/JS) | Componente personalizado para dictar equipos por voz. |
| **Audio y Efectos** | Web Audio API (JS nativo) | Sonidos sintetizados en tiempo real (sin archivos de audio externos) para clics, alertas y goles. |

---

## 3. Fuentes de Datos y Estrategia de Caché

La aplicación **no requiere bases de datos SQL tradicionales ni credenciales pagas** para su funcionamiento básico. Se alimenta de fuentes abiertas y públicas:

1. **ESPN APIs (Endpoints públicos no oficiales):**
   - NBA Scoreboard, rosters, calendarios, box scores históricos, posiciones y lesiones.
   - Fútbol Scoreboard en vivo, plantillas y fichas de partidos multitorneo.
2. **Football-Data.co.uk:**
   - Archivos CSV históricos y en curso con estadísticas detalladas (tiros, tiros al arco, faltas, córners, tarjetas, goles al descanso) y cuotas de cierre/apertura de múltiples casas de apuestas.
   - `fixtures.csv` para próximos partidos y cuotas vigentes.
3. **Tennis-Data.co.uk / Repositorios GitHub:**
   - Resultados detallados de tenis ATP y WTA.
   - `martj42/international_results`: Historial de partidos de fútbol entre selecciones nacionales desde 1872.

### Mecanismos de Caché y Persistencia:
- **`st.cache_data(ttl=...)`**: Para datos volátiles (marcadores en vivo: 10-60 seg; estadísticas: 1 hora; calendarios: 24 horas).
- **Caché en Disco (`.cache_box/`):** Almacenamiento local de JSONs con los box scores de partidos de la NBA terminados para evitar peticiones redundantes.
- **Archivos JSON de Estado Local:**
  - `favoritos_equipos.json`: IDs de equipos favoritos del usuario.
  - `favoritos_jugadores.json`: IDs de jugadores favoritos del usuario.
  - `alertas_config.json`: Umbrales y minutos de anticipación para las notificaciones.
  - `alertas_estado.json`: Huella de las últimas alertas procesadas para evitar duplicados.

---

## 4. Índice Detallado de Archivos y Funcionalidades

### 4.1. Núcleo, Configuración y Navegación
- **`app.py`**: Punto de entrada de la aplicación (`streamlit run app.py`). Configura la vista (`st.set_page_config`), carga el sistema de diseño jerárquico (`diseno`, `estilos`, `efectos`, `pulido`, `movimiento`), construye el menú lateral y despacha a la sección activa: Inicio, En vivo, NBA, Fútbol, Tenis y Diagnóstico.
- **`secciones.py`**: Define las constantes maestras y descripciones de las secciones del menú lateral.
- **`common.py`**: Utilidades compartidas: sesión HTTP (`requests.Session`) con headers de navegador y reintentos automáticos, zona horaria estándar (`America/Santiago`), funciones de normalización de cadenas de texto y algoritmos puros para el cálculo de rachas (`buscar_rachas`, `racha_actual`, `racha_maxima`, `racha_resultado`).
- **`config.toml`**: Configuración del tema base de Streamlit (fondo claro, color primario `#4F46E5`).
- **`requirements.txt`**: Lista de dependencias del entorno Python.
- **`LEEME.txt`**: Manual de usuario final para ejecución en Windows/Mac/Linux y notas de versión.

### 4.2. Sistema de Diseño, Estilos e Interactividad (Frontend Pipeline)
La interfaz pasa por una cascada de capas especializadas para lograr un aspecto de producto profesional y no de prototipo:
- **`diseno.py`**: Sistema base de diseño. Transforma las tablas de Streamlit para que no parezcan hojas de cálculo, inyectando estilos limpios, etiquetas coloreadas para resultados y barras de progreso.
- **`estilos.py`**: Cargador central de hojas de estilo CSS. Administra e inyecta tokens de diseño y componentes desde la carpeta `css/` o cadenas por defecto incluidas en el código.
- **`efectos.py`**: Dinamismo por deporte. Asigna paletas cromáticas específicas (Naranja cancha para NBA, Verde césped para Fútbol, Rojo marcador para En vivo), franjas animadas con balones vectoriales SVG y fondos temáticos.
- **`pulido.py`**: Capa de armonización y sobriedad visual. Define navegación en 3 niveles (menú lateral, control segmentado de vistas y pestañas con subrayado fino), superficies limpias y variables CSS `--pl-*`.
- **`movimiento.py`**: Capa avanzada de interacción. Controla aurora ambiental ligera con aceleración GPU, transiciones de entrada, efecto 3D *tilt* en tarjetas, sintetizador de sonidos mediante Web Audio API (sin archivos MP3) y animaciones de festejo de goles/victorias con confeti y destellos.
- **Archivos CSS de soporte (`tokens.css`, `hoy.css`, `equipos.css`, `escudos.css`, `ficha_linea.css`):** Hojas de estilos complementarias para componentes de marcadores, tarjetas de equipos y fichas de líneas.

### 4.3. Inicio, Favoritos y Alertas
- **`inicio.py`**: Portada de la app. Ofrece un resumen del día (partidos en vivo, por jugar y finalizados por deporte) descargados concurrentemente con `ThreadPoolExecutor`, accesos directos y comprobación de estado de fuentes.
- **`portada.py`**: Cuadrícula de tarjetas personalizadas en la página de inicio que muestra los equipos y jugadores favoritos del usuario, su forma reciente, bajas médicas y próximos compromisos.
- **`favoritos.py`**: Módulo de persistencia y gestión de equipos y jugadores guardados en `favoritos_equipos.json` y `favoritos_jugadores.json`.
- **`favoritos_datos.py`**: Descarga asíncrona y paralela de estadísticas recientes, lesiones y calendarios específicos para los favoritos seleccionados.
- **`alertas.py`**: Monitor en segundo plano que se ejecuta cada 60 s en el menú lateral. Detecta partidos próximos a empezar, cambios en el parte de lesionados y movimientos significativos en las líneas de cuotas.

### 4.4. Módulo NBA (Baloncesto)
- **`nba_panel.py`**: Orquestador central de la sección NBA. Divide las herramientas en dos grupos: **Equipos** (*Líneas*, *Planteles*, *Próximos*) y **Jugadores** (*Estadísticas* y *Cara a Cara*). Incluye un botón para purgar cachés volátiles.
- **`nba.py`**: Funciones maestras de NBA: descarga de equipos con respaldo estático de las 30 franquicias, panel de partidos en vivo, cálculo del ranking Elo histórico y seguimiento de rachas entre equipos.
- **`nba_hoy.py`**: Tablero completo de los partidos del día (~3.100 líneas). Integra cuotas de apuestas, cálculo de Elo, lista de lesionados categorizados por severidad (Out, Doubtful, Questionable, Day-to-Day), comparativa táctica y recomendaciones de picks.
- **`nba_equipos.py`**: Vista de exploración de franquicias: selector interactivo de escudos, plantilla completa dividida por posiciones (Bases, Aleros, Pívots) y fichas individuales de atletas.
- **`nba_jugadores.py`**: Análisis profundo de jugadores (~2.200 líneas). Permite comparar hasta 4 jugadores simultáneamente, evaluar métricas (PTS, REB, AST, 3PM, STL, BLK, combinadas P+R+A) en ventanas de 5 a 25 partidos y visualizar tendencias.
- **`nba_h2h_jugadores.py`**: Comparador Head-to-Head directo entre dos jugadores cuando juegan como rivales o cuando comparten quinteto como compañeros de equipo.
- **`nba_extra.py`**: Métricas avanzadas: clasificaciones por conferencia, cálculo de eficiencia ofensiva/defensiva por 100 posesiones, los Cuatro Factores de Dean Oliver, registros ATS (*Against The Spread*) y Over/Under. Gestiona la caché en `.cache_box/`.
- **`nba_profundo.py`**: Módulo de lógica algorítmica pura. Analiza el impacto numérico de las bajas de jugadores titulares, la absorción de uso ofensivo por suplentes, el rendimiento de jugadores recién regresados de lesión y los puntos concedidos por posición defensiva.
- **`nba_sim_jugadores.py`**: Motor de simulación Monte Carlo (4.000 iteraciones por partido). Modela el marcador cuarto a cuarto, distribuye los minutos por tramos de 6 min considerando titulares, rotaciones y minutos de la basura (*garbage time*), y simula estadísticas individuales mediante distribuciones Gamma-Poisson.
- **`nba_combinada.py`**: Analizador de parlays/combinadas. Permite ingresar selecciones manualmente o subir una fotografía de la boleta para ser procesada con visión por IA (Claude), validando la probabilidad histórica individual y conjunta de cada pata del boleto.

### 4.5. Módulo Fútbol (Soccer)
- **`football.py`**: Módulo principal de fútbol. Integra el marcador en vivo de ligas mundiales (ESPN), carga de ligas europeas y americanas (football-data.co.uk), cálculo de Elo para clubes y selecciones, y navegación entre submódulos.
- **`football_lineas.py`**: Panel de análisis de líneas de apuestas (~1.600 líneas). Permite evaluar mercados de goles (totales, por equipo, 1er/2do tiempo), Ambos Anotan (BTTS), saques de esquina, tarjetas amarillas/rojas, faltas y tiros al arco en los últimos 5 a 25 encuentros.
- **`football_proximos.py`**: Análisis predictivo de los partidos venideros mediante un **modelo bivariado de Poisson**. Proyecta goles esperados (*xG* simplificado), probabilidad 1X2, marcador exacto más probable, líneas recomendadas y picks automáticos de jugadores (tiros, tiros al arco, goles).
- **`football_tarjeta.py`**: Generador HTML/CSS independiente de la tarjeta visual de fútbol con temática de césped verde, mostrando porcentajes de acierto en anillo, barras de partidos recientes con insignias L/V y factor de días de descanso.
- **`football_recientes.py`**: Rastreador de partidos multitorneo vía ESPN. Asegura que los últimos partidos de un equipo incluyan Champions League, copas nacionales y amistosos, y no únicamente la liga doméstica de football-data.
- **`football_extra.py`**: Análisis de cuotas de mercado (Pinnacle, Bet365, medias del mercado), eliminación de margen de la casa de apuestas (*vig*), cálculo de ROI histórico por estrategia, matrices de transición primer tiempo / final y estadísticas detalladas por árbitro.
- **`confederaciones.py`**: Clasificación geográfica de selecciones nacionales por confederación (CONMEBOL, UEFA, CONCACAF, CAF, AFC, OFC).
- **`selecciones.py`**: Diccionario de normalización de nombres de países de inglés a español, códigos de banderas ISO (`flagcdn.com`) y abreviaturas oficiales.

### 4.6. Módulo Tenis
- **`tennis_lineas.py`**: Módulo integral de análisis de líneas de tenis (~1.100 líneas). Totalmente desacoplado. Carga datos de ATP y WTA desde `tennis-data.co.uk` y analiza mercados de total de games, games por jugador, hándicaps de games, games en el 1er set, tie-breaks, sets corridos y victorias. Incluye desglose por superficie (Dura, Arcilla, Césped) y cálculo de fatiga acumulada en los últimos 7 y 14 días.

### 4.7. Tarjetas y Gráficos Reutilizables
- **`ficha_equipos.py`**: Motor de visualización y cálculo de líneas para equipos (~1.800 líneas). Genera la tarjeta analítica con anillo de acierto, gráfico de barras horizontales/verticales, filtros de local/visita, rachas y cálculo de medias/medianas.
- **`ficha_linea.py`**: Componente de tarjeta de línea para jugadores individuales (~1.500 líneas). Permite ajustar líneas personalizadas con decimales (.5), evalúa escenarios *Over/Under* excluyendo empates (*pushes*) y resalta el historial frente al rival de turno.
- **`graficos.py`**: Constructores de gráficos Altair puros para tendencias de jugadores con medias móviles a 5 y 10 partidos.
- **`tarjeta_imagen.py`**: Renderizador fotográfico mediante Pillow para crear imágenes descargables con diseño profesional para compartir en mensajería.
- **`index.html` / `voz_equipos/index.html`**: Componente Web de reconocimiento por voz para seleccionar equipos mediante el micrófono sin escribir.

### 4.8. Diagnóstico y Pruebas Unitarias
- **`diagnostico.py`**: Panel de salud del sistema. Hace peticiones de sondeo concurrentes a todas las APIs externas (ESPN, football-data, GitHub), midiendo latencia en segundos, códigos de estado HTTP y peso de los datos.
- **`test_logica.py`**: Pruebas sobre transferencia de estados entre vistas y funciones analíticas de gráficos.
- **`test_nba_profundo.py`**: Pruebas con partidos sintéticos sobre el cálculo de tendencias, bajas y regresos de lesión.
- **`test_football_lineas.py`**: Pruebas sobre la preparación de tablas de goles, córners y tarjetas por partido.
- **`test_ficha_equipos.py` & `test_ficha_linea.py`**: Pruebas de la lógica de evaluación de apuestas *Over/Under/Push*.
- **`test_football_extra.py`**: Pruebas sobre la normalización de probabilidades implícitas de casas de apuestas.

---

## 5. Modelos Matemáticos y Algoritmos Implementados

1. **Modelo de Poisson para Fútbol (`football_proximos.py`):**
   - Calcula el poder ofensivo y defensivo de cada equipo basándose en una ventana de los últimos 15 partidos ponderados exponencialmente (factor de decaimiento `0.9` por partido previo).
   - Ajusta los goles esperados ($\lambda_{\text{local}}, \lambda_{\text{visita}}$) según la ventaja de localía y la fuerza del rival.
   - Aplica la distribución de Poisson para construir la matriz de probabilidad de marcadores ($0-0$ hasta $10-10$), derivando las probabilidades de 1X2, Más/Menos de 2.5 goles y Ambos Anotan.
   - Incorpora penalización por ausencias de jugadores clave en la plantilla de ESPN.

2. **Simulación Monte Carlo NBA (`nba_sim_jugadores.py`):**
   - Ejecuta **4.000 simulaciones** por encuentro.
   - Modela el ritmo de posesiones y los minutos de juego esperados en bloques de 6 minutos.
   - Aplica distribuciones Gamma-Poisson para modelar la dispersión en tiros de tres, rebotes y robos.
   - Redistribuye automáticamente las posesiones y tiros cuando un titular clave figura como baja confirmada.

3. **Sistema de Puntuación Elo:**
   - Implementado en `nba.py` y `football.py`.
   - Modela el ranking dinámico de franquicias y selecciones a lo largo del tiempo para evaluar si una victoria fue contra un rival de élite o un equipo en reconstrucción.

4. **Probabilidades Implícitas sin Margen (*Overround Removal* en `football_extra.py`):**
   - Convierte las cuotas decimales $O_i$ a probabilidades implícitas brutas: $p_i^* = \frac{1}{O_i}$.
   - Elimina el margen de beneficio de la casa de apuestas mediante normalización: $p_i = \frac{p_i^*}{\sum p_i^*}$, obteniendo la probabilidad real estimada por el mercado.

---

## 6. Convenciones de Sesión y Flujo de Datos

- **`st.session_state`**:
  - `seccion`: Sección principal activa (`🏠 Inicio`, `🔴 En vivo`, `🏀 NBA`, etc.).
  - `fav_equipos`: Lista de IDs de equipos favoritos.
  - `jug_favoritos`: Lista de IDs de atletas favoritos.
  - Parámetros de filtros de partidos: `eq_a`, `eq_b`, `mercado`, `linea_val`.
- **Ejecución de la Aplicación:**
  ```bash
  streamlit run app.py
  ```
- **Ejecución de la Suite de Pruebas:**
  ```bash
  pytest
  ```

---
*Este documento resume la totalidad de la estructura funcional, técnica y matemática de la aplicación.*
