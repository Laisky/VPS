# docker build . -f ramjet/Dockerfile -t ppcelery/ramjet
FROM ppcelery/gargantua-base:20200102

RUN git clone https://github.com/Laisky/ramjet.git --depth=1 -b develop /app && \
    cd app && \
    pip install -r requirements.txt

WORKDIR /app

ENTRYPOINT ["python", "-m", "ramjet"]
