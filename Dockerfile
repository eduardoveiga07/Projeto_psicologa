FROM python:3.12-slim
WORKDIR /code
RUN apt-get update && apt-get install -y --no-install-recommends locales \
 && sed -i 's/# *pt_BR.UTF-8 UTF-8/pt_BR.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen pt_BR.UTF-8 \
 && rm -rf /var/lib/apt/lists/*
ENV LANG=pt_BR.UTF-8 LC_ALL=pt_BR.UTF-8
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
ENV PYTHONPATH=/code
# Privilegio minimo: cria e usa usuario nao-root.
RUN useradd -m appuser && chown -R appuser /code
USER appuser
EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", "--server.address=0.0.0.0", "--server.port=8501"]
