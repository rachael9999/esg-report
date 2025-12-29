FROM python:3.10
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY . .
CMD ["uvicorn", "esg_graph:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
