FROM ppcelery/edgelessrt-dev:20221201 AS build

RUN wget https://github.com/edgelesssys/ego/releases/download/v1.0.1/ego_1.0.1_amd64.deb
RUN apt install -y ./ego_*_amd64.deb

FROM ppcelery/edgelessrt-dev:20221201 AS dev
LABEL description="EGo is an SDK to build confidential enclaves in Go - as simple as conventional Go programming!"
COPY --from=build /opt/ego /opt/ego
ENV PATH=${PATH}:/opt/ego/bin
ENTRYPOINT [ "/bin/bash", "-l", "-c" ]

FROM ppcelery/edgelessrt-deploy:20221201 AS deploy
LABEL description="A runtime version of EGo to handle enclave-related tasks such as signing and running Go SGX enclaves."
COPY --from=build /opt/ego/bin /opt/ego/bin
COPY --from=build /opt/ego/share /opt/ego/share
ENV PATH=${PATH}:/opt/ego/bin
ENTRYPOINT [ "/bin/bash", "-l", "-c" ]
