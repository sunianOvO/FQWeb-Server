# 番茄Web节点池服务

## 使用

注意：请将下面所有命令中的fqweb_token修改为你自己设置的Token，这个Token可以用来执行一些管理员命令

### python运行
```shell
git clone https://github.com/fengyuecanzhu/FQWeb-Server.git
# 切换进入项目目录
cd FQWeb-Server
# 安装python依赖
pip install -r requirements.txt
# 启动
python server.py fqweb_token
```

### Docker运行
```shell
docker run -d --name=fqweb-server --restart=always -p 5000:5000 -v /data:/app/data -e TZ="Asia/Shanghai" -e FQWEB_TOKEN="fqweb_token" fengyuecanzhu/fqweb-server
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
      - FQWEB_TOKEN=fqweb_token
    volumes:
      - /data:/app/data  # 映射本地的/data目录到容器内的/app/data目录
```