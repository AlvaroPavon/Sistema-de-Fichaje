# 1. Usamos una versión ligera de Python oficial
FROM python:3.11-slim

# 2. Le decimos a Docker que trabaje dentro de una carpeta llamada /app
WORKDIR /app

# 3. Copiamos nuestro archivo de requisitos primero
COPY requirements.txt .

# 4. Instalamos las herramientas (Flask)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiamos el resto de nuestro código
COPY . .

# 6. Abrimos el puerto 5000 para poder ver la web
EXPOSE 5000

# 7. El comando que se ejecutará al encender el contenedor
CMD ["python", "fichador.py"]