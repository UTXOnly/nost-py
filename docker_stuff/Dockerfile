FROM python:3.9

WORKDIR /app

COPY requirements.txt .
ENV PATH "$PATH:/usr/local/bin"
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade pip

COPY ./python_stuff .

CMD ["ddtrace-run","python", "ws3.py"]