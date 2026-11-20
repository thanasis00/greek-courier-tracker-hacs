# Renders the card for the visual test (tests/visual/run.py) with the same
# browser and fonts on every machine
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
# The image has the browsers of this Playwright version, not the package
RUN pip install --no-cache-dir --break-system-packages playwright==1.49.1 pillow==11.0.0
WORKDIR /work
