FROM python:3.13-alpine

WORKDIR /ctf

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]