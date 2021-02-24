FROM ubuntu:20.04
#folder structure
#/SpacerBackend/
#├── chc-tools
#├── Dockerfile
#├── pobvis
#│   └── app
#│       ├── exp_db
#│       ├── main.py
#│       ├── media
#│       ├── reinit_db.sh
#│       ├── settings.py
#│       ├── start_server.sh
#│       └── utils
#└── z3s
RUN apt update && apt install -y wget unzip
RUN wget https://github.com/Z3Prover/z3/releases/download/z3-4.8.9/z3-4.8.9-x64-ubuntu-16.04.zip -O z3s.zip
RUN unzip -j z3s.zip -d z3s/
#install other stuffs
RUN apt update && apt install -y vim python3-pip apt-transport-https sqlite3

#copy just the requirements to install
#so that we dont have to rebuild with changes in the code
COPY ./pobvis/requirements.txt /SpacerBackend/pobvis/requirements.txt
COPY ./chc-tools/requirements.txt /SpacerBackend/chc-tools/requirements.txt

WORKDIR /SpacerBackend/pobvis/app/
RUN pip3 install -r /SpacerBackend/chc-tools/requirements.txt
RUN pip3 install -r /SpacerBackend/pobvis/requirements.txt

#copy the code folder
COPY ./pobvis /SpacerBackend/pobvis
COPY ./chc-tools /SpacerBackend/chc-tools

#init db
RUN ./reinit_db.sh

ENV PYTHONPATH "/SpacerBackend/chc-tools:/SpacerBackend/pobvis:/SpacerBackend/z3s/NhamZ3/build/python"

ENTRYPOINT python3 -u main.py -z3 /z3s/z3 
