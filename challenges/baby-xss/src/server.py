import os
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
port = os.getenv('PORT', 80)

@app.route('/')
def hello():
    name = request.args.get('name', 'guest')
    return f'Hello {name}!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)