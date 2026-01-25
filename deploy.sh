#!/bin/bash
set -e

echo "==== Installing Python dependencies ===="
pip install -r requirements.txt

echo "==== Building React frontend ===="
cd frontend
npm ci
npm install
npm run build

cd ..


# After building Vite, collectstatic will handle moving files from frontend/dist
# based on the STATICFILES_DIRS setting in settings.py

echo "==== Collecting static files ===="
python manage.py collectstatic --noinput

echo "==== Applying migrations ===="
python manage.py migrate
