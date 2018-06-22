FROM ppcelery/gargantua-base
RUN apk update && apk upgrade && \
    apk add --no-cache bash git ca-certificates && \
    update-ca-certificates

RUN git clone https://github.com/Laisky/laisky-blog.git && \
    cd laisky-blog && \
    git checkout develop && \
    pip install -r requirements.txt

RUN cd laisky-blog && git pull && git checkout origin/dist && \
    python setup.py develop

ENTRYPOINT run_gargantua
