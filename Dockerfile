FROM alpine as build

RUN apk add --no-cache python3 python3-dev build-base libffi-dev openssl-dev linux-headers git && \
    python3 -m ensurepip && \
    rm -r /usr/lib/python*/ensurepip && \
    pip3 install --upgrade pip setuptools wheel && \
    if [ ! -e /usr/bin/pip ]; then ln -s pip3 /usr/bin/pip ; fi && \
    if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3 /usr/bin/python; fi && \
    rm -r /root/.cache

COPY . /sonny
WORKDIR /sonny

RUN pip install -e . && python setup.py bdist_wheel



FROM alpine

COPY --from=build /sonny/dist/*.whl .
RUN apk add --no-cache python3 python3-dev build-base libffi-dev openssl-dev linux-headers git nmap && \
    python3 -m ensurepip && \
    rm -r /usr/lib/python*/ensurepip && \
    pip3 install --upgrade pip setuptools wheel && \
    pip3 install --upgrade *.whl && \
    if [ ! -e /usr/bin/pip ]; then ln -s pip3 /usr/bin/pip ; fi && \
    if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3 /usr/bin/python; fi && \
    rm -r /root/.cache && rm *.whl

WORKDIR /root
CMD ["true"]
