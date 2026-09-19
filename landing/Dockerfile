# Nothing to install: the page is static and the signup endpoint uses only the
# Python standard library.
FROM python:3.12-slim

WORKDIR /app
COPY . .

# PORT is supplied by the platform. See server.py.
CMD ["python", "server.py"]
