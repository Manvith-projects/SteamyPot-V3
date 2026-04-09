FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY Churn-Prediction/requirements.txt Churn-Prediction/requirements.txt
COPY Driver-Allocation/requirements.txt Driver-Allocation/requirements.txt
COPY Dynamic-Pricing/requirements.txt Dynamic-Pricing/requirements.txt
COPY ETA-Predictor/requirements.txt ETA-Predictor/requirements.txt
COPY Food-Assistant/requirements.txt Food-Assistant/requirements.txt
COPY Recommendation_Engine/requirements.txt Recommendation_Engine/requirements.txt
COPY Recovery-Agent/requirements.txt Recovery-Agent/requirements.txt
COPY Review-Summarizer/requirements.txt Review-Summarizer/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9001

CMD ["python", "gateway.py"]
