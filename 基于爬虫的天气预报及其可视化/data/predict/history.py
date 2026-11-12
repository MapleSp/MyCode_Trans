import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import random
import re
import time
import pickle
import os


file_path = os.path.join(os.path.dirname(__file__), 'fake_useragent.json')

# 初始化 UserAgent
ua = UserAgent(file_path)


# 获取随机 User-Agent 头部
def get_header():
    headers = {
        'User-Agent': ua.random
    }
    return headers


# 获取城市的拼音和中文名称列表
def get_citys(soup):
    pinyin_list = []
    chinese_name_list = []
    data_table = soup.find_all('table')[0]
    city_columns = data_table.find_all('a')

    get_city_pinyin_pattern = re.compile(r'(?<=href=").*(?=/index.html)')
    get_city_chinese_pattern = re.compile(r'(?<=>).*(?=</a>)')

    for data_item in city_columns:
        data_item = str(data_item)
        pinyin = get_city_pinyin_pattern.findall(data_item)
        if not pinyin:
            continue
        pinyin = pinyin[0]
        chinese_name = get_city_chinese_pattern.findall(data_item)[0]
        pinyin_list.append(pinyin)
        chinese_name_list.append(chinese_name)

    return pinyin_list, chinese_name_list


# 获取当前月份的数据
def get_cur_month_data(soup):
    month_data_list = []
    day_res_pattern = re.compile(r'(?<=">).*(?=</div>)')
    for item1 in soup.find_all("li"):
        item2 = item1.find_all("div")
        if """<div class="th200">""" in str(item2):
            day_list = [day_res_pattern.findall(str(item))[0] for item in item2]
            month_data_list.append(day_list)
    return month_data_list


# 控制爬虫频率
def random_sleep():
    time.sleep(round(random.uniform(1.72, 5.19), 3))


# 长睡眠
def long_sleep():
    time.sleep(round(random.uniform(32.74, 64.75), 3))


# 获取当前时间
def get_now_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))


# 保存变量到文件
def save_variable(v, filename):
    with open(filename, 'wb') as f:
        pickle.dump(v, f)


# 从文件加载变量
def load_variable(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)


def main():
    target = "http://lishi.tianqi.com/"
    req = requests.get(url=target, headers=get_header(), timeout=60)
    soup = BeautifulSoup(req.text, 'html.parser')

    pinyin_list, chinese_name_list = get_citys(soup)
    city_pinyin_chinese = {chinese: pinyin for pinyin, chinese in zip(pinyin_list, chinese_name_list)}

    pinyin_list = pinyin_list[2:]
    random.shuffle(pinyin_list)

    processed_city_month = set()
    error_city_month = set()

    month_list = [f"20210{i}" for i in range(1, 8)]
    city_datas = {}

    c = 0
    print("爬虫启动时间=", get_now_time())
    start_time = time.time()

    for name in pinyin_list:
        if name not in city_datas:
            city_datas[name] = {}

        for month in month_list:
            query_item = f"{name}|{month}"
            if query_item in processed_city_month:
                continue

            target = f"https://lishi.tianqi.com/{name}/{month}.html"
            try:
                req = requests.get(url=target, headers=get_header(), timeout=60)
                req.raise_for_status()
            except Exception as e:
                print(query_item, e)
                error_city_month.add(query_item)
                continue

            soup = BeautifulSoup(req.text, 'html.parser')
            month_data_list = get_cur_month_data(soup)
            city_datas[name][month] = month_data_list
            processed_city_month.add(query_item)
            c += 1

            if c % 10 == 0:
                cur_time = time.time()
                remaining_time = (len(pinyin_list) * len(month_list) - c) * (cur_time - start_time) / c
                print(len(city_datas), round(remaining_time / 60, 5))

            random_sleep()

            if c % 1001 == 0:
                long_sleep()

            if c % 5000 == 0:
                file_name = f"city_datas_{c // 5000}.pkl"
                save_variable(city_datas, file_name)

    file_name = "city_datas_all.pkl"
    save_variable(city_datas, file_name)


if __name__ == "__main__":
    main()
