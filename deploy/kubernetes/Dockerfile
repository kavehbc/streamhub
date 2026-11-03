# The Streamhub image plus kubectl, for "runtime": "kubernetes" apps.
#   make k8s-image    (or: docker build -t kavehbc/streamhub:2.3.0 . &&
#                          docker build --build-arg BASE=kavehbc/streamhub:2.3.0 -t streamhub-kubectl:2.3.0 deploy/kubernetes)
ARG BASE=kavehbc/streamhub:2.3.0
FROM ${BASE}

ARG KUBECTL_VERSION=v1.36.1
ARG TARGETARCH=amd64
USER root
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl', '/usr/local/bin/kubectl')" \
    && chmod 755 /usr/local/bin/kubectl
USER streamhub
