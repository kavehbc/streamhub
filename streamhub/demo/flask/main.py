import os

import click
from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
# Streamhub serves the app under /<app_id>/ and sends X-Forwarded-Prefix, so url_for() builds correct links.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.route('/')
def hello_world():
    return f'Hello, World! <a href="{url_for("hello_check")}">check</a>'


@app.route('/check/')
def hello_check():
    return 'Hello, World! This is the check section.'


@app.route('/go/')
def go():
    return redirect(url_for("hello_check"))


@app.route('/health/')
def health():
    # Polled by Streamhub (the app's health_path) for readiness and periodic health checks.
    return 'ok'


@click.command()
@click.option('--port', default=5000, help='Server port')
@click.option('--app_id', default='', help='Streamhub app id')
def run(port, app_id):
    # STREAMHUB_HOST is 127.0.0.1 for local processes and 0.0.0.0 inside a container.
    app.run(host=os.environ.get('STREAMHUB_HOST', '127.0.0.1'), port=port)


if __name__ == "__main__":
    run()
