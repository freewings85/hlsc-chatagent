import os
from configparser import ConfigParser
from dotenv import load_dotenv
import nacos
import socket
import logging

logger = logging.getLogger(__name__)

# 根据命令行参数获取环境名称，如果没有传入参数则默认为 'development'
env_name = os.getenv('ACTIVE', 'local')
env_file = f'.env.{env_name}'

# 加载指定环境的 .env 文件
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    print(f"未找到 {env_file} 文件，使用默认配置。")
    load_dotenv()
    
# 从环境变量中获取 Nacos 配置信息
SERVER_ADDRESSES = os.getenv('NACOS_SERVER_ADDRESSES')
NAMESPACE = os.getenv('NACOS_NAMESPACE')
DATA_ID = os.getenv('NACOS_DATA_ID')
GROUP = os.getenv('NACOS_GROUP')
NACOS_USERNAME = os.getenv('NACOS_USERNAME', '')
NACOS_PASSWORD = os.getenv('NACOS_PASSWORD', '')


SERVICE_NAME=os.getenv('ApplicationName')
API_PORT=os.getenv('API_PORT')
API_NAME=os.getenv('API_NAME')
API_VERSION=os.getenv('API_VERSION')

USE_NACOS=os.getenv('USE_NACOS', 'TRUE')

# 创建 Nacos 客户端实例
client = None
if USE_NACOS == 'TRUE':
    client = nacos.NacosClient(SERVER_ADDRESSES, namespace=NAMESPACE, username=NACOS_USERNAME, password=NACOS_PASSWORD)

def get_nacos_config():
    if USE_NACOS == 'FALSE':
        return {}
    try:
        config_content = client.get_config(DATA_ID, GROUP)
        if config_content is None:
            print(f"Nacos 返回空配置（DATA_ID={DATA_ID}, GROUP={GROUP}），跳过")
            return {}
        if DATA_ID.endswith('.properties'):
            # 使用 configparser 解析，保持大小写
            config = ConfigParser(strict=False)
            # 让 configparser 保持大小写
            config.optionxform = lambda option: option  # 关键：保持原始大小写

            # 模拟 .properties 文件格式
            fake_section = '[DEFAULT]\n' + config_content
            config.read_string(fake_section)

            # 获取配置（保持原始大小写）
            properties_dict = dict(config['DEFAULT'])
            # 将这些配置设置到环境变量中
            for key, value in properties_dict.items():
                os.environ[key] = value
            return properties_dict;
        else:
            print("不支持的配置文件格式。")
    except Exception as e:
        print(f"获取配置时出错：{e}")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def register_service():
    if USE_NACOS == 'FALSE':
        return
    # 注册服务到 Nacos
    try:
        API_IP=get_local_ip()
        result = client.add_naming_instance(service_name=SERVICE_NAME, ip=API_IP, port=API_PORT)
        if result:
            logger.info(f"服务 {SERVICE_NAME} 注册到 Nacos 成功，地址: {API_IP}:{API_PORT}")
        else:
            logger.warning(f"服务 {SERVICE_NAME} 注册到 Nacos 失败，地址: {API_IP}:{API_PORT}")
    except Exception as e:
        logger.error(f"服务注册到 Nacos 时出错: {e}")

def deregister_service():
    if USE_NACOS == 'FALSE':
        return
    # 取消服务注册
    try:
        API_IP=get_local_ip()
        result = client.remove_naming_instance(service_name=SERVICE_NAME, ip=API_IP, port=API_PORT)
        if result:
            logger.info(f"服务 {SERVICE_NAME} 从 Nacos 取消注册成功，地址: {API_IP}:{API_PORT}")
        else:
            logger.warning(f"服务 {SERVICE_NAME} 从 Nacos 取消注册失败，地址: {API_IP}:{API_PORT}")
    except Exception as e:
        logger.error(f"服务从 Nacos 取消注册时出错: {e}")

        


nacosConfig = get_nacos_config()