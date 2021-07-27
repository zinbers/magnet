import base64
import io
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex, QObject, Slot, Property, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from loguru import logger
from qrcode import QRCode, constants
from requests import head

from config import Config
from crawler import run_crawler
from resource import qInitResources


class QDataListModel(QAbstractListModel):
    NAME = Qt.UserRole + 1000
    TIME = Qt.UserRole + 1001
    SIZE = Qt.UserRole + 1002
    HOT = Qt.UserRole + 1003
    MAGNET = Qt.UserRole + 1004

    def __init__(self, model):
        QAbstractListModel.__init__(self)
        self.model = model

    def rowCount(self, parent = None) -> int:
        return len(self.model)

    def roleNames(self):
        return {
            self.NAME:   b'name',
            self.TIME:   b'time',
            self.SIZE:   b'size',
            self.HOT:    b'hot',
            self.MAGNET: b'magnet',
        }

    def data(self, index: QModelIndex, role: int = None):
        index = index.row()
        row = self.model[index]

        return row[str(self.roleNames()[role], 'utf-8')]


class MainWindow(QObject):
    def __init__(self, app: QGuiApplication, config: Config):
        QObject.__init__(self)
        self._app = app
        self._config = config
        self._pool = ThreadPoolExecutor()
        self._search_result_list = QDataListModel([])

    @Slot(str, int, result = str)
    def test_proxy(self, server, port):
        logger.info(f'检查代理是否符合规则: {server}:{port}')
        # 校验代理地址
        server_reg = re.compile(r'^((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})(\.((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})){3}')
        if server != 'localhost' and server_reg.match(server) is None:
            logger.error(f'代理校验失败, 代理地址不符合规则')
            return 'failed'
        # 校验代理端口号
        if port == 0:
            logger.error(f'代理校验失败, 代理端口不符合规则')
            return 'failed'

        logger.info(f'检查代理是否可用: {server}:{port}')
        proxies = {'http': f'http://{server}:{port}', 'https': f'http://{server}:{port}'}
        try:
            r = head('https://www.google.com/', proxies = proxies, timeout = 5)
            if r.status_code == 200:
                logger.success('代理校验成功')
                return 'success'
            else:
                logger.error('代理校验失败')
                return 'failed'
        except Exception as e:
            logger.error(f'代理校验失败: {e}')
            return 'failed'

    @Slot(str, result = str)
    def magnet_qr_code(self, magnet):
        logger.info(f'生成二维码: {magnet}')
        qr = QRCode(
            version = 1,
            error_correction = constants.ERROR_CORRECT_L,
            box_size = 10,
            border = 1,
        )
        qr.make(fit = True)
        qr.add_data(magnet)
        qr_img = qr.make_image()

        buf = io.BytesIO()
        qr_img.save(buf, format = 'PNG')
        image_stream = buf.getvalue()

        return f'data:image/png;base64,{base64.b64encode(image_stream).decode()}'

    @Slot(str)
    def download(self, magnet):
        print('调用迅雷下载')
        # os.system(f'"D:/apps/Thunder/Program/ThunderStart.exe" {magnet}')
        print(magnet)

    @Slot(str)
    def copy_to_clipboard(self, magnet):
        logger.info(f'复制内容: {magnet} 到剪切板')
        cb = self._app.clipboard()
        cb.setText(magnet)

    def search_done(self, future):
        if future.result() is None:
            # 通知页面数据加载失败（忽视编辑器莫名其妙的警告）
            # noinspection PyUnresolvedReferences
            self.loadStateChanged.emit('error')
        else:
            self._search_result_list = QDataListModel(future.result())

            # 通知页面数据加载完成（忽视编辑器莫名其妙的警告）
            # noinspection PyUnresolvedReferences
            self.loadStateChanged.emit('loaded')

    @Slot(str, str)
    def search(self, key, search_terms):
        logger.info(f'提交搜索任务, 网站规则: {key}, 搜索词: {search_terms}')
        # 提交任务
        self._pool.submit(run_crawler, key, search_terms, '1', '').add_done_callback(self.search_done)
        # 通知页面处于加载状态（忽视编辑器莫名其妙的警告）
        # noinspection PyUnresolvedReferences
        self.loadStateChanged.emit('loading')

    loadStateChanged = Signal(str)

    # 绑定QML数据
    @Property(QObject, constant = False, notify = loadStateChanged)
    def search_result_list(self):
        return self._search_result_list


def main():
    logger.remove(handler_id = None)
    logger.add(sys.stdout)
    logger.add(sink = 'log/magnet.log', rotation = '100 MB', retention = '30 days',
               enqueue = True, compression = 'zip', level = 'DEBUG', encoding = 'utf-8',
               format = '{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {file}:{line} | {name}:{function} | {message}')

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    # 初始化资源
    qInitResources()

    # 绑定视图
    backend = MainWindow(app, Config())
    engine.rootContext().setContextProperty('backend', backend)
    engine.load('qrc:/main.qml')

    if not engine.rootObjects():
        return -1

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
