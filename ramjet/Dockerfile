FROM python:3.6.5-alpine3.7
RUN apk update && apk upgrade && \
    apk add --no-cache bash git ca-certificates python-dev \
    gcc g++ make libxml2-dev libffi-dev libxslt-dev && \
    update-ca-certificates

RUN git clone https://github.com/Laisky/ramjet.git /app && \
    cd app && \
    git checkout master && \
    pip install -r requirements.txt

WORKDIR /app

CMD python -m ramjet
