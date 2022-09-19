FROM python:3.9-slim-buster

WORKDIR /mock-lti-consumer

COPY . .
RUN pip3 install -r requirements.txt

EXPOSE 8080

ENTRYPOINT ["flask", "run", "--host", "0.0.0.0", "--port", "8080"]
