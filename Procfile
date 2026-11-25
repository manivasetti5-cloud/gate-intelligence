release: python -m flask db upgrade && python -m flask seed
web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 "app:create_app('production')"
