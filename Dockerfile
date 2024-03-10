FROM tiangolo/uvicorn-gunicorn-fastapi:python3.8

COPY . /app

WORKDIR /app

RUN pip install --no-cache-dir --upgrade -r requirements.txt
RUN pip install fastapi uvicorn

CMD ["uvicorn", "main:fastapi_app", "--host 0.0.0.0", "--port 8050"]