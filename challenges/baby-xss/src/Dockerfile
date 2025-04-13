FROM python:3.13-alpine AS build

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-alpine

WORKDIR /ctf
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY server.py .

CMD ["python", "server.py"]