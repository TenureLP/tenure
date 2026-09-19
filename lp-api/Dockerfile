# Nothing to install: the service uses only the Python standard library.
# The image is explicit rather than detected, so the build does not depend on a
# platform guessing the language, the entrypoint or the Python version.
FROM python:3.12-slim

WORKDIR /app
COPY . .

# PORT is supplied by the platform; the server binds every interface when it
# sees one and stays on loopback otherwise. See lpval/server.py.
CMD ["python", "-m", "lpval", "serve"]
