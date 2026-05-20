FROM python:3.10-slim

WORKDIR /app

# 设置时区为亚洲/上海，确保日志时间正确
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 代码通过 compose 挂载映射，无需 COPY
# 默认启动命令
CMD ["python", "generate_cover.py"]
