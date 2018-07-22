FROM gcr.io/kubeflow-images-public/tensorflow-1.8.0-notebook-cpu

RUN pip install ktext annoy sklearn nltk
RUN mkdir /issues
WORKDIR /issues
COPY . /issues
CMD python train.py
