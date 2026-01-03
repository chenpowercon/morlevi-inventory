FROM python:3.9-slim

# התקנת Chrome
RUN apt-get update && apt-get install -y wget gnupg2 curl unzip && rm -rf /var/lib/apt/lists/*
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get update && apt-get install -y google-chrome-stable

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# כאן השינוי החשוב: שם הקובץ שלך
CMD ["python", "MORINV.py"]