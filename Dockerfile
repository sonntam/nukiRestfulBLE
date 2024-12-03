FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y bluez libbluetooth-dev git
#RUN apt-get install -y python3.11-dev

WORKDIR /app

RUN pip install --upgrade pip 

COPY ./requirements.txt /app/
RUN pip install -r requirements.txt
RUN rm requirements.txt

COPY ./restserver.py /app/
COPY ./job_queue.py /app/

EXPOSE 51001

CMD ["python", "restserver.py"]
#CMD ["tail", "-f", "/dev/null"]
