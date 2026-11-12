# Atmos 智能气象台

这是一个基于 Flask、网页爬取与 SQLite 的城市天气可视化项目。页面不仅展示天气，还会把温度、体感温度、湿度、风向风力、紫外线、空气质量、能见度和七日预报组合成可执行的保暖、避暑、防晒、防雨、防风与健康建议。

## 主要功能

- 城市搜索联想：支持中文名称、城市后缀、常用拼音和轻微错字纠正。
- 浏览器定位：通过经纬度反查行政区，在线反查失败时自动匹配最近的主要城市。
- 实时天气：从中国天气网采集实时观测、官方生活指数、预警和七日预报。
- 智能分析：基于多指标规则生成舒适度、风险摘要、穿衣、活动与出行建议。
- 数据可视化：动态天气视觉、核心指标卡、七日预报和温度趋势曲线。
- 完整状态：搜索加载、页面骨架屏、空状态、错误建议、历史缓存提示和演示数据降级。
- 缓存持久化：内存 TTL 缓存与 SQLite 快照双层缓存，在线失败自动回退历史数据。
- 稳定性保障：有界线程队列、同城请求合并、API 滑动窗口限流、指数退避重试、统一异常与请求编号。
- 响应式设计：适配桌面、平板和手机，并支持减少动画的系统偏好。

## 启动

建议使用 Python 3.10 及以上版本。

```powershell
pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:5000>。

### 分享给同一局域网的朋友

双击项目根目录中的 `一键启动分享网站.bat`。脚本会自动把服务绑定到局域网，并在窗口中显示类似下面的分享地址：

```text
http://192.168.1.30:5000
```

朋友需要与你在同一 Wi-Fi 或局域网中，并且你的电脑和启动窗口必须保持运行。Windows 防火墙第一次询问时，请允许 Python 访问“专用网络”。

如需分享给不在同一局域网的朋友，可使用 Cloudflare Tunnel：

```powershell
cloudflared tunnel --url http://localhost:5000
```

也可以直接双击 `一键启动公网分享.bat`。脚本会启动本地网站并建立临时 SSH 隧道，在窗口中输出类似下面的公网地址：

```text
https://random-name.lhr.life
```

公网地址会周期性变化。只要不关闭公网分享窗口，朋友就可以通过该 HTTPS 地址访问。临时隧道停止后需要重新启动并发送新地址。

旧的 `data/dayseven/OnlineData.py` 入口仍可使用：

```powershell
python .\data\dayseven\OnlineData.py
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 主要接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/cities?query=北` | 城市联想与错字容错 |
| `GET /api/weather/北京` | 完整天气、预报、指数和智能建议 |
| `GET /api/location?lat=39.9&lon=116.4` | 坐标反查城市 |
| `GET /api/compare?cities=北京,上海` | 多城市并行查询 |
| `GET /api/recent` | 当前客户端最近查询 |
| `GET /api/health` | 缓存、队列和数据库健康状态 |
| `GET /api/meta` | API 元信息 |

## 目录结构

```text
app.py                     # 应用启动入口
weather_app/
  factory.py               # 应用工厂与组件装配
  routes.py                # 页面与 JSON API
  scraper.py               # 网页爬取、解析和演示数据
  service.py               # 多级缓存与业务编排
  advisor.py               # 智能气象建议规则引擎
  cities.py                # 城市检索、联想和纠错
  database.py              # SQLite 持久化
  cache.py                 # 内存 TTL 缓存
  queue.py                 # 有界并发队列与请求合并
  rate_limit.py            # API 限流
  location.py              # 定位反查与离线最近城市
templates/                 # HTML 页面
static/css/style.css       # 页面视觉
static/js/                 # API、联想、首页和详情页逻辑
tests/test_app.py          # 自动化测试
instance/weather.db        # 运行时生成的天气快照数据库
logs/weather.log           # 运行时滚动日志
```

## 配置

常用环境变量：

| 变量 | 默认值 | 说明 |
| --- | ---: | --- |
| `WEATHER_CACHE_TTL` | `900` | 天气缓存秒数 |
| `WEATHER_STALE_TTL_HOURS` | `168` | 历史快照最长可回退小时数 |
| `WEATHER_HTTP_TIMEOUT` | `10` | 上游请求超时秒数 |
| `WEATHER_HTTP_RETRIES` | `2` | 上游失败重试次数 |
| `WEATHER_QUEUE_WORKERS` | `4` | 天气抓取线程数 |
| `WEATHER_QUEUE_CAPACITY` | `32` | 队列最大等待数 |
| `WEATHER_RATE_LIMIT` | `30` | 每客户端每分钟天气查询数 |
| `SEARCH_RATE_LIMIT` | `120` | 每客户端每分钟城市联想数 |

生活建议用于日常出行参考，重要决策请以当地气象部门发布的临近预报和预警为准。
