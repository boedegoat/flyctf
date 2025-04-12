import os
from flask import Flask, request

app = Flask(__name__)
port = int(os.getenv('PORT', 80))

@app.route('/')
def hello():
    name = request.args.get('name', 'guest')
    return f"""
<h1>Hello {name}!</h1>
<p>Try to play with "name" param!</p>
<a href="/report">Report to admin<a/>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)