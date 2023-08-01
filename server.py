import datetime
import os
import random
import re
import threading
import time
import json

import requests
import schedule
from flask import Flask, request, redirect

app = Flask(__name__)

# 数据文件保存目录
data_dir = "data"
os.makedirs(data_dir, exist_ok=True)

# Node pool and recycle bin to store domain names
node_pool = []
recycle_bin = []

# 统计数据变量
total_requests = 0
daily_requests = 0
shared_nodes = 0
active_nodes = 0
start_time = time.time()


# 日志打印
def log(msg):
    utc_time = datetime.datetime.utcnow()
    china_time = utc_time + datetime.timedelta(hours=8)
    print(f"[{china_time.strftime('%Y.%m.%d %H:%M:%S')}] {msg}")


# 保存统计数据到文件的函数
def save_statistics():
    stats = {
        "total_requests": total_requests,
        "daily_requests": daily_requests,
        "shared_nodes": shared_nodes,
        "active_nodes": active_nodes,
        "start_time": start_time
    }
    with open(os.path.join(data_dir, "statistics.json"), "w") as file:
        json.dump(stats, file)


# 从文件加载统计数据的函数
def load_statistics():
    try:
        with open(os.path.join(data_dir, "statistics.json"), "r") as file:
            stats = json.load(file)
            global total_requests, daily_requests, shared_nodes, active_nodes, start_time
            total_requests = stats.get("total_requests", 0)
            daily_requests = stats.get("daily_requests", 0)
            shared_nodes = stats.get("shared_nodes", 0)
            active_nodes = stats.get("active_nodes", 0)
            start_time = stats.get("start_time", time.time())
    except FileNotFoundError:
        pass


# Load node pool and recycle bin from files (if available)
def load_data_from_file():
    try:
        with open(os.path.join(data_dir, "node_pool.json"), "r") as node_pool_file:
            global node_pool
            node_pool = json.load(node_pool_file)
    except FileNotFoundError:
        pass

    try:
        with open(os.path.join(data_dir, "recycle_bin.json"), "r") as recycle_bin_file:
            global recycle_bin
            recycle_bin = json.load(recycle_bin_file)
    except FileNotFoundError:
        pass


# Save node pool and recycle bin to files
def save_data_to_file():
    with open(os.path.join(data_dir, "node_pool.json"), "w") as node_pool_file:
        json.dump(node_pool, node_pool_file)

    with open(os.path.join(data_dir, "recycle_bin.json"), "w") as recycle_bin_file:
        json.dump(recycle_bin, recycle_bin_file)


# 在服务器启动时加载统计数据
load_statistics()
load_data_from_file()


# 每天零点清零日请求次数
def reset_daily_requests():
    global daily_requests
    daily_requests = 0


# 在每天零点调用 reset_daily_requests 函数
schedule.every().day.at("00:00").do(reset_daily_requests)


# Helper function to check if a domain is accessible (e.g., not 404)
def is_domain_accessible(domain):
    try:
        url = f'http://{domain["domain"]}/content'
        response = requests.get(url)
        if response.status_code == 200:
            domain['timestamp'] = time.time()
            return True
        else:
            return False
    except Exception:
        return False


def is_valid_domain_name(domain):
    # 定义域名的正则表达式模式
    domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'

    # 使用re.match函数进行匹配
    if re.match(domain_pattern, domain):
        return True
    else:
        return False


# Helper function to manage domain status in the node pool and recycle bin
def manage_domains():
    while True:
        try:
            # Move domains from node pool to recycle bin if they are not accessible
            for domain in node_pool:
                if not is_domain_accessible(domain):
                    recycle_bin.append(domain)
                    node_pool.remove(domain)

            # Move domains from recycle bin back to node pool if they become accessible again
            for domain in recycle_bin:
                if is_domain_accessible(domain):
                    node_pool.append(domain)
                    recycle_bin.remove(domain)

            # Remove domains from recycle bin if they are inaccessible for more than an hour
            for domain in recycle_bin:
                if time.time() - domain['timestamp'] >= 3600:
                    recycle_bin.remove(domain)

            # Update statistics
            global shared_nodes, active_nodes
            shared_nodes = len(node_pool) + len(recycle_bin)
            active_nodes = len(node_pool)

            # Save statistics to file
            save_statistics()
            # Save data to file
            save_data_to_file()
            # 启动定时任务
            schedule.run_pending()
            # Wait for 10 seconds before rechecking domains
            time.sleep(10)
        except Exception as e:
            log(e)


# Start the domain management thread
domain_manager_thread = threading.Thread(target=manage_domains, name="Check domain", daemon=True)
domain_manager_thread.start()


# Helper function to check if a domain exists in node pool or recycle bin
def is_domain_exists(domain):
    for node in node_pool:
        if node['domain'] == domain:
            return True
    return False


# 用户上传域名到节点池的接口
@app.route('/upload', methods=['GET'])
def upload_domain():
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    domain = request.args.get('domain')
    if not domain:
        return '未提供域名', 400

    if not is_valid_domain_name(domain):
        return '不合法的域名', 400

    if is_domain_exists(domain):
        return '该域名已存在于节点池', 400

    # 从回收站中移除该域名（如果存在）
    for node in recycle_bin:
        if node['domain'] == domain:
            recycle_bin.remove(node)
            break

    node_pool.append({'domain': domain, 'timestamp': time.time()})
    return '域名已成功上传', 200


# 用户随机获取节点池中的域名（负载均衡）
@app.route('/random', methods=['GET'])
def get_random_domain():
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    if not node_pool:
        return '没有可用的域名', 404

    domain = random.choice(node_pool)
    return domain['domain'], 200


# 重定向至随机节点池中的域名（负载均衡），重定向需要保留URL和参数进行重定向
@app.route('/<path:any_url>', methods=['GET'])
def redirect_to_random_domain(any_url):
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    if not node_pool:
        return '没有可用的域名', 404

    domain = random.choice(node_pool)
    redirect_url = f"http://{domain['domain']}/{any_url}?{request.query_string.decode('utf-8')}"
    return redirect(redirect_url, 302)


# 获取所有活跃节点的域名，换行输出
@app.route('/reading', methods=['GET'])
def get_active_nodes():
    global total_requests, daily_requests, active_nodes
    total_requests += 1
    daily_requests += 1

    if not node_pool:
        return '没有可用的活跃节点', 404

    active_node_domains = '\n'.join(domain['domain'] for domain in node_pool)
    return active_node_domains, 200, {'Content-Type': 'text/plain; charset=utf-8'}


# 获取统计数据的接口
@app.route('/stats', methods=['GET'])
def get_statistics():
    global total_requests, daily_requests, shared_nodes, active_nodes, start_time
    uptime_hours = round((time.time() - start_time) / 3600, 2)
    stats_text = (
        f"总请求次数：{total_requests}\n"
        f"日请求次数：{daily_requests}\n"
        f"共享节点数：{shared_nodes}\n"
        f"活跃节点数：{active_nodes}\n"
        f"运行时间（小时）：{uptime_hours}"
    )
    return stats_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
