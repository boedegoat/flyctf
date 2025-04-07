FROM python:3.9-slim

WORKDIR /challenge_app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ .

EXPOSE 80

CMD ["python", "server.py"]