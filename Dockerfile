FROM python:3.9-slim

# 1. התקנת כלים בסיסיים (כולל gnupg לניהול מפתחות אבטחה)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 2. הוספת המפתח של גוגל כרום (בשיטה החדשה שעוקפת את השגיאה)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg

# 3. הגדרת המקור להורדת כרום
RUN echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# 4. התקנת גוגל כרום עצמו
RUN apt-get update && apt-get install -y google-chrome-stable --no-install-recommends && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# הפקודה להרצת הסקריפט שלך
CMD ["python", "morinv.py"]

