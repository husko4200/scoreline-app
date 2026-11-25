# Imagen base oficial de Python ligera
FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y habilitar salida directa por consola
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar librerías
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Cloud Run inyecta la variable $PORT automáticamente (por defecto 8080)
ENV PORT=8080
EXPOSE 8080

# Comando de arranque para producción
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
