# 番茄Web节点池服务

## 使用

### python运行
```shell
git clone https://github.com/fengyuecanzhu/FQWeb-Server.git
# 切换进入项目目录
cd FQWeb-Server
# 安装python依赖
pip install -r requirements.txt
# 启动
python server.py
```

### Docker运行
```shell
docker run -d --name=fqweb-server --restart=always -p 5000:5000 -v /data:/app/data -e TZ="Asia/Shanghai" fengyuecanzhu/fqweb-server
```

### Docker Compose
```yaml
version: '3'
services:
  web:
    image: fengyuecanzhu/fqweb-server
    container_name: fqweb-server
    ports:
      - "5000:5000"
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - /data:/app/data  # 映射本地的/data目录到容器内的/app/data目录
```