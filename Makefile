# Use the project's virtualenv python/pip by default (works on Windows).
# Override with `make PYTHON=python3` on Unix if you prefer that.
PYTHON ?= .venv/Scripts/python
PIP ?= .venv/Scripts/pip

mig:
	$(PYTHON) manage.py makemigrations
	$(PYTHON) manage.py migrate
admin:
	$(PYTHON) manage.py createsuperuser  --username admin --email  admin@mail.com

req:
	$(PIP) freeze > requirements.txt

install-req:
	$(PIP) install -r requirements.txt

static:
	$(PYTHON) manage.py collectstatic --noinput