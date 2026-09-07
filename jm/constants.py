"""JMComic 模块常量"""

# 默认配置
DEFAULT_CONFIG = {
    "jm_enabled": True,
    "jm_send_file": True,
    "jm_max_file_size": 10,  # 文件大小限制（MB），0 表示不限制
    "jm_cookies": "",
    "jm_proxy": "",
    "jm_timeout": 20,
    "jm_retry_times": 3,
    "jm_image_threads": 16,
    "jm_photo_threads": 4,
    "jm_max_concurrent": 1,
}
