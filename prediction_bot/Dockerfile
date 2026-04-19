FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p prediction_bot/data
EXPOSE 4001
CMD ["python", "-m", "prediction_bot.main"]
