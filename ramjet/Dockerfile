FROM ppcelery/gargantua-base

RUN git clone https://github.com/Laisky/ramjet.git /app && \
    cd app && \
    git checkout develop && \
    pip install -r requirements.txt

WORKDIR /app

ENTRYPOINT python -m ramjet
