一个零依赖、纯本地的跨设备文件互传系统。手机、平板、电脑，扫码即连，聊天传文件一站式搞定。

环境要求

* 一台电脑（Windows / macOS / Linux 均可）
* Python 3.8 或以上版本
* 如果要使用 PDF 转换功能，需安装 [LibreOffice](https://www.libreoffice.org/download/download/)

安装与运行

1. 下载项目

bash
git clone https://github.com/你的用户名/仓库名.git
cd 仓库名
或者直接下载 ZIP 压缩包并解压。

2. 安装依赖

bash
pip install -r requirements.txt
3. 启动服务

bash
python app.py
4. 加入会话

终端会打印类似以下信息：

# text

会话码: 385720
请在浏览器打开: http://192.168.1.5:8080
二维码地址: http://192.168.1.5:8080/qr
===

电脑端：浏览器打开显示的地址，输入会话码进入

手机 / 平板：确保连接同一个 Wi-Fi，扫描终端二维码或手动输入地址，输入会话码进入

如果手机无法访问，请检查电脑防火墙设置，允许 Python 的网络访问。

