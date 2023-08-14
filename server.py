import datetime
import os
import re
import sys
import threading
import time
import json

import requests
import schedule
from flask import Flask, request, redirect

app = Flask(__name__)

# 管理员TOKEN
FQWEB_TOKEN = os.environ.get("FQWEB_TOKEN")

# 数据文件保存目录
data_dir = "data"
os.makedirs(data_dir, exist_ok=True)

# Node pool and recycle bin to store domain names
node_pool = []
recycle_bin = []
tokens = []
block_domains = []

# 统计数据变量
total_requests = 0
daily_requests = 0
yesterday_requests = 0
shared_nodes = 0
active_nodes = 0
start_time = time.time()

# 节点的最大载荷数
max_load_per_node = 8
delay_time = 4
max_remove_time = 60 * 30
allow_urls = ['search', 'info', 'catalog', 'content', 'reading/bookapi/bookmall/cell/change/v1/',
              'reading/bookapi/new_category/landing/v/']


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
        "yesterday_requests": yesterday_requests,
        "shared_nodes": shared_nodes,
        "active_nodes": active_nodes,
        "start_time": start_time
    }
    with open(os.path.join(data_dir, "statistics.json"), "w") as file:
        json.dump(stats, file)
        # log(f'保存统计数据')


# 从文件加载统计数据的函数
def load_statistics():
    try:
        with open(os.path.join(data_dir, "statistics.json"), "r") as file:
            stats = json.load(file)
            global total_requests, daily_requests, shared_nodes, active_nodes, start_time
            total_requests = stats.get("total_requests", 0)
            daily_requests = stats.get("daily_requests", 0)
            yesterday_requests = stats.get("yesterday_requests", 0)
            shared_nodes = stats.get("shared_nodes", 0)
            active_nodes = stats.get("active_nodes", 0)
            start_time = stats.get("start_time", time.time())
            log(f'加载统计数据')
    except FileNotFoundError:
        pass


# Load node pool and recycle bin from files (if available)
def load_data_from_file():
    try:
        with open(os.path.join(data_dir, "node_pool.json"), "r") as node_pool_file:
            global node_pool
            node_pool = json.load(node_pool_file)
            log(f'加载节点池数据')
    except FileNotFoundError:
        pass

    try:
        with open(os.path.join(data_dir, "recycle_bin.json"), "r") as recycle_bin_file:
            global recycle_bin
            recycle_bin = json.load(recycle_bin_file)
            log(f'加载回收站数据')
    except FileNotFoundError:
        pass

    try:
        with open(os.path.join(data_dir, "tokens.json"), "r") as tokens_file:
            global tokens
            tokens = json.load(tokens_file)
            log(f'加载tokens数据')
    except FileNotFoundError:
        pass

    try:
        with open(os.path.join(data_dir, "block_domains.json"), "r") as block_domains_file:
            global block_domains
            block_domains = json.load(block_domains_file)
            log(f'加载block_domains数据')
    except FileNotFoundError:
        pass

    for node in node_pool + recycle_bin:
        node['load'] = 0


# Save node pool and recycle bin to files
def save_data_to_file():
    with open(os.path.join(data_dir, "node_pool.json"), "w") as node_pool_file:
        json.dump(node_pool, node_pool_file)
        # log(f'保存节点池数据')

    with open(os.path.join(data_dir, "recycle_bin.json"), "w") as recycle_bin_file:
        json.dump(recycle_bin, recycle_bin_file)
        # log(f'保存回收站数据')

    with open(os.path.join(data_dir, "tokens.json"), "w") as tokens_file:
        json.dump(tokens, tokens_file)
        # log(f'保存tokens数据')


# 在服务器启动时加载统计数据
load_statistics()
load_data_from_file()


# 每天零点清零日请求次数
def reset_daily_requests():
    global daily_requests
    yesterday_requests = daily_requests
    daily_requests = 0
    log(f'日请求清零')


# 在每天零点调用 reset_daily_requests 函数
schedule.every().day.at("00:00").do(reset_daily_requests)


# Helper function to check if a domain is accessible (e.g., not 404)
def is_domain_accessible(domain):
    try:
        # log(f'检测节点是否有效：{domain["domain"]}')
        url = f'http://{domain["domain"]}/content'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            domain['timestamp'] = time.time()
            return True
        else:
            return False
    except Exception as e:
        log(f'检测节点{domain["domain"]}出错：{e}')
        return False


def is_valid_domain_name(domain):
    # 定义域名的正则表达式模式
    domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?::(\d{1,5}))?$'

    # 使用re.match函数进行匹配
    if re.match(domain_pattern, domain):
        return True
    else:
        return False


# Helper function to manage domain status in the node pool and recycle bin
def manage_domains():
    delta = 0
    while True:
        try:
            start_check_time = time.time()
            # Move domains from node pool to recycle bin if they are not accessible
            for domain in node_pool:
                if domain['domain'] in block_domains:
                    node_pool.remove(domain)
                    continue
                if not is_domain_accessible(domain):
                    recycle_bin.append(domain)
                    node_pool.remove(domain)
                else:
                    if 'token' in domain and domain['token']:
                        add_or_update_token(domain['token'], (10 + delta) * 3)

            # Move domains from recycle bin back to node pool if they become accessible again
            for domain in recycle_bin:
                if is_domain_accessible(domain):
                    node_pool.append(domain)
                    recycle_bin.remove(domain)
                    if 'token' in domain and domain['token']:
                        add_or_update_token(domain['token'], (10 + delta) * 3)

            # Remove domains from recycle bin if they are inaccessible for more than an hour
            for domain in recycle_bin:
                if time.time() - domain['timestamp'] >= max_remove_time:
                    recycle_bin.remove(domain)

            # Remove tokens if they are invalid
            for token in tokens:
                if token['expire_time'] < time.time():
                    tokens.remove(token)

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

            # 完成
            delta = int(time.time() - start_check_time)
            log(f"manage_domains执行完成，耗时：{delta}秒")

            # Wait for 10 seconds before rechecking domains
            time.sleep(10)
        except Exception as e:
            log(f'manage_domains出错：{e}')


# Start the domain management thread
domain_manager_thread = threading.Thread(target=manage_domains, name="Check domain", daemon=True)
domain_manager_thread.start()


# Helper function to check if a domain exists in node pool or recycle bin
def is_domain_exists(domain):
    for node in node_pool:
        if node['domain'] == domain:
            return True
    return False


def is_domain_exists_by_token(token):
    for node in node_pool:
        if 'token' in node and node['token'] == token:
            return True
    return False


def is_valid_token(token):
    pattern = r'^[A-Za-z0-9]+$'
    # 使用re.match函数进行匹配
    if re.match(pattern, token):
        return True
    else:
        return False


# 添加或更新token
def add_or_update_token(token, add_time=10):
    if not is_valid_token(token):
        return
    log(f'添加或更新token：{token}')
    for token_obj in tokens:
        if token_obj['token'] == token:
            if token_obj['expire_time'] < time.time():
                token_obj['expire_time'] = time.time() + add_time
            else:
                token_obj['expire_time'] = token_obj['expire_time'] + add_time
            return
    tokens.append({'token': token, 'expire_time': time.time() + add_time})


# 检测token是否有效
@app.route('/valid', methods=['GET'])
def token_valid():
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    token = request.args.get('token')
    return is_token_valid(token)


# 判断token是否有效
def is_token_valid(token):
    if not token:
        return '未提供token', 400
    # log(f'判断token是否有效：{token}')
    for token_obj in tokens:
        if token_obj['token'] == token:
            if token_obj['expire_time'] < time.time():
                return 'token已失效', 400
            else:
                return f'有效的token，过期时间：' \
                       f'{time.strftime("%Y.%m.%d %H:%M:%S", time.localtime(token_obj["expire_time"]))}', 200
    return 'token不存在', 400


# 用户上传域名到节点池的接口
@app.route('/upload', methods=['GET'])
def upload_domain():
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    domain = request.args.get('domain')
    token = request.args.get('token')
    if not domain:
        return '未提供域名', 400

    if not is_valid_domain_name(domain):
        return '不合法的域名', 400

    if domain in block_domains:
        return '域名已被封禁', 400

    if is_domain_exists(domain):
        return '该域名已存在于节点池', 400

    # 从回收站中移除该域名（如果存在）
    for node in recycle_bin:
        if node['domain'] == domain:
            recycle_bin.remove(node)
            break
    if token and is_valid_token(token):
        add_or_update_token(token)
        node_pool.append({'domain': domain, 'token': token, 'timestamp': time.time()})
    else:
        node_pool.append({'domain': domain, 'timestamp': time.time()})
    return '域名已成功上传', 200


# 重定向至随机节点池中的域名（负载均衡），重定向需要保留URL和参数进行重定向
@app.route('/<path:any_url>', methods=['GET'])
def redirect_to_random_domain(any_url):
    global total_requests, daily_requests, max_load_per_node
    total_requests += 1
    daily_requests += 1

    token = request.headers.get('token')
    if not node_pool:
        return '没有可用的域名', 404

    if any_url not in allow_urls:
        return "不合法的url", 404

    if is_token_valid(token)[1] == 200:
        nodes = node_pool.copy()
        nodes.sort(key=lambda x: x.get('load', 0))
        domain = nodes[0]
        redirect_url = f"http://{domain['domain']}/{any_url}?{request.query_string.decode('utf-8')}"
        return redirect(redirect_url, 302)

    # 寻找非满载的节点进行重定向，如果节点池中的节点均满载，则持续等待有非满载的节点进行重定向
    nodes = node_pool.copy()
    while True:
        nodes.sort(key=lambda x: x.get('load', 0))
        domain = nodes[0]
        if 'load' not in domain:
            domain['load'] = 0
        if domain['load'] < max_load_per_node:
            redirect_url = f"http://{domain['domain']}/{any_url}?{request.query_string.decode('utf-8')}"
            increase_load(domain)
            return redirect(redirect_url, 302)
        # 若所有节点都满载，则等待0.1秒后重新检查
        time.sleep(0.1)


# 用户随机获取节点池中的域名（负载均衡）
@app.route('/random', methods=['GET'])
def get_random_domain():
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    token = request.headers.get('token')
    if not node_pool:
        return '没有可用的域名', 404

    if is_token_valid(token)[1] == 200:
        nodes = node_pool.copy()
        nodes.sort(key=lambda x: x.get('load', 0))
        domain = nodes[0]
        increase_load(domain)
        return f"http://{domain['domain']}", 200

    # 寻找非满载的节点进行选取，如果节点池中的节点均满载，则持续等待有非满载的节点进行选取
    nodes = node_pool.copy()
    while True:
        nodes.sort(key=lambda x: x.get('load', 0))
        domain = nodes[0]
        if 'load' not in domain:
            domain['load'] = 0
        if domain['load'] < max_load_per_node:
            increase_load(domain)
            return f"http://{domain['domain']}", 200
        # 若所有节点都满载，则等待0.1秒后重新检查
        time.sleep(0.1)


def increase_load(domain):
    global delay_time
    domain['load'] += 1
    # delay_time秒后将载荷减1
    threading.Timer(delay_time, lambda: reduce_load(domain)).start()
    # log(f'节点载荷加一：{domain}')


def reduce_load(domain):
    domain['load'] -= 1
    # log(f'节点载荷减一：{domain}')


# 获取所有活跃节点的域名，换行输出
@app.route('/status', methods=['GET'])
def get_active_nodes():
    global total_requests, daily_requests, active_nodes, FQWEB_TOKEN
    total_requests += 1
    daily_requests += 1
    token = request.args.get("token")
    if not FQWEB_TOKEN:
        return '未设置TOKEN', 404
    if not token or token != FQWEB_TOKEN:
        return '无效的token', 404
    if not node_pool:
        return '没有可用的节点', 404

    active_node_domains = '\n'.join(f'{domain["domain"]}: {domain.get("load", 0)}' for domain in node_pool)
    return active_node_domains, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/check', methods=['GET'])
def check_domain():
    global total_requests, daily_requests
    total_requests += 1
    daily_requests += 1

    domain = request.args.get('domain')
    token = request.args.get('token')
    if domain:
        if domain in block_domains:
            return '节点已被封禁', 200

        if is_domain_exists(domain):
            return '节点状态：在线', 200

    if token:
        if is_domain_exists_by_token(token):
            return '节点状态：在线', 200

    return '节点不存在或者已离线', 200


# 获取可用节点数
@app.route('/available', methods=['GET'])
def get_active_nodes_num():
    return f'{active_nodes}', 200


# 获取统计数据的接口
@app.route('/stats', methods=['GET'])
def get_statistics():
    global total_requests, daily_requests, shared_nodes, active_nodes, start_time, max_load_per_node
    uptime_hours = round((time.time() - start_time) / 3600, 2)
    stats_text = (
        f"总请求次数：{total_requests}\n"
        f"日请求次数：{daily_requests}\n"
        f"昨日请求数：{yesterday_requests}\n"
        f"共享节点数：{shared_nodes}\n"
        f"活跃节点数：{active_nodes}\n"
        f"请求队列数：{get_all_loads()}/{active_nodes * max_load_per_node}\n"
        f"运行时间（小时）：{uptime_hours}"
    )
    return stats_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/block', methods=['GET'])
def block_domain():
    global total_requests, daily_requests, active_nodes, FQWEB_TOKEN
    total_requests += 1
    daily_requests += 1
    token = request.args.get("token")
    if not FQWEB_TOKEN:
        return '未设置TOKEN', 404
    if not token or token != FQWEB_TOKEN:
        return '无效的token', 404
    domain = request.args.get('domain')
    if not domain:
        return '未提供域名', 400

    block_domains.append(domain)
    with open(os.path.join(data_dir, 'block_domains.json'), 'w') as block_domains_file:
        json.dump(block_domains, block_domains_file)

    return '添加黑名单成功', 400


@app.route('/clear/blocks', methods=['GET'])
def clear_block_domains():
    global total_requests, daily_requests, active_nodes, FQWEB_TOKEN
    total_requests += 1
    daily_requests += 1
    token = request.args.get("token")
    if not FQWEB_TOKEN:
        return '未设置TOKEN', 404
    if not token or token != FQWEB_TOKEN:
        return '无效的token', 404

    block_domains.clear()
    with open(os.path.join(data_dir, 'block_domains.json'), 'w') as block_domains_file:
        json.dump(block_domains, block_domains_file)

    return '黑名单清理成功', 400


@app.route('/get/blocks', methods=['GET'])
def get_block_domains():
    global total_requests, daily_requests, active_nodes, FQWEB_TOKEN
    total_requests += 1
    daily_requests += 1
    token = request.args.get("token")
    if not FQWEB_TOKEN:
        return '未设置TOKEN', 404
    if not token or token != FQWEB_TOKEN:
        return '无效的token', 404
    if not block_domains:
        return '没有封禁的域名', 404
    return '\n'.join(block_domains), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/', methods=['GET'])
def main_page():
    return redirect('https://github.com/fengyuecanzhu/FQWeb', 302)


def get_all_loads():
    loads = 0
    for domain in node_pool:
        if 'load' in domain:
            loads += domain['load']
    return loads


if __name__ == '__main__':
    if len(sys.argv) > 1:
        FQWEB_TOKEN = sys.argv[1]
    app.run(host='0.0.0.0', port=5000)
