"""Optional per-user singleton activation for desktop-launcher starts."""
import getpass
import json
import os

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def instance_name():
    user = str(os.getuid()) if hasattr(os, 'getuid') else getpass.getuser()
    return f'eyeglow-egobody-{user}'


class SingleInstance:
    """Own a local activation endpoint or notify the process that already does."""

    def __init__(self, name=None):
        self.name = name or instance_name()
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept_connections)
        self.connections = set()
        self.window = None
        self.pending_token = None

    def start(self):
        if self._notify_existing():
            return False
        if self.server.listen(self.name):
            return True
        # A simultaneous first launch may have won listen() immediately after
        # our initial probe. Give it a chance to accept before treating the
        # endpoint as stale.
        for _ in range(5):
            if self._notify_existing(200):
                return False
        QLocalServer.removeServer(self.name)
        if self.server.listen(self.name):
            return True
        if self._notify_existing(500):
            return False
        raise OSError(f'Could not create application activation endpoint: {self.server.errorString()}')

    def _notify_existing(self, timeout_ms=100):
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(timeout_ms):
            return False
        message = json.dumps({
            'activate': True,
            'xdg_activation_token': os.environ.get('XDG_ACTIVATION_TOKEN', ''),
        }).encode() + b'\n'
        socket.write(message)
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True

    def _accept_connections(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.connections.add(socket)
            socket.readyRead.connect(lambda connection=socket: self._read(connection))
            socket.disconnected.connect(lambda connection=socket: self._drop(connection))
            if socket.bytesAvailable():
                self._read(socket)

    def _read(self, socket):
        for line in bytes(socket.readAll()).splitlines():
            try:
                message = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if message.get('activate'):
                self._activate(message.get('xdg_activation_token', ''))

    def _drop(self, socket):
        self.connections.discard(socket)
        socket.deleteLater()

    def set_window(self, window):
        self.window = window
        if self.pending_token is not None:
            token, self.pending_token = self.pending_token, None
            self._activate(token)

    def _activate(self, token):
        if self.window is None:
            self.pending_token = token
            return
        if token:
            # Qt Wayland consumes the launch context when requesting activation.
            os.environ['XDG_ACTIVATION_TOKEN'] = token
        QTimer.singleShot(0, self._raise_window)

    def _raise_window(self):
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        handle = self.window.windowHandle()
        if handle is not None:
            handle.requestActivate()

    def close(self):
        self.server.close()
