FROM public.ecr.aws/lambda/python:3.11

# Εγκαθιστούμε pip και dependencies
RUN pip install --upgrade pip

# Αντιγραφή requirements και εγκατάσταση
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Αντιγραφή υπόλοιπου κώδικα
COPY . ./

#  build tag για να το βλέπουμε στο "/" response
ARG BUILD_TAG=local-dev
ENV BUILD_TAG=${BUILD_TAG}

ENV PYTHONPATH="/var/task"

# Entry point: η Mangum μετατρέπει το FastAPI app σε handler για Lambda
CMD ["app.main.handler"]
