# 1. Use a lightweight Python base image
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy the requirements file and install Python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Download Chromium and install all the heavy Linux system dependencies!
RUN playwright install chromium
RUN playwright install-deps chromium

# 5. Copy the rest of your backend code
COPY . .

# 6. Launch the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]