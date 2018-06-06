FROM ppcelery/gargantua-base
RUN apk update && apk upgrade && \
    apk add --no-cache bash git ca-certificates && \
    update-ca-certificates

RUN cd laisky-blog && git pull && git checkout origin/dist && \
    python setup.py develop

CMD run_gargantua
