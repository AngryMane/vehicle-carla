import asyncio
import uuid
import logging
from typing import Dict, List, Optional, Set
import grpc
from grpc import aio

# 生成されたプロトコルバッファファイルをインポート
try:
    import sys
    sys.path.append('generated')
    from vehicle_shadow import signal_pb2, signal_pb2_grpc, types_pb2
except ImportError as e:
    print(f"警告: 生成されたプロトコルバッファファイルが見つかりません: {e}")
    print("python generate_proto.py を実行してファイルを生成してください")
    # フォールバック用のダミーインポート
    signal_pb2 = None
    signal_pb2_grpc = None
    types_pb2 = None

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SignalStore:
    """信号データを管理するストアクラス"""
    
    def __init__(self):
        self.signals: Dict[str, signal_pb2.Signal] = {}
        self.locks: Dict[str, str] = {}  # path -> token
        self.subscribers: Dict[str, Set[asyncio.Queue]] = {}  # path -> set of queues
        
    def get_signal(self, path: str) -> Optional[signal_pb2.Signal]:
        """指定されたパスの信号を取得"""
        return self.signals.get(path)
    
    def set_signal(self, path: str, signal: signal_pb2.Signal) -> None:
        """信号を設定"""
        self.signals[path] = signal
        # サブスクライバーに通知
        self._notify_subscribers(path, signal)
    
    def is_locked(self, path: str) -> bool:
        """信号がロックされているかチェック"""
        return path in self.locks
    
    def lock_signal(self, path: str, token: str) -> bool:
        """信号をロック"""
        if path in self.locks:
            return False
        self.locks[path] = token
        return True
    
    def unlock_signal(self, path: str, token: str) -> bool:
        """信号のロックを解除"""
        if path not in self.locks or self.locks[path] != token:
            return False
        del self.locks[path]
        return True
    
    def add_subscriber(self, path: str, queue: asyncio.Queue) -> None:
        """サブスクライバーを追加"""
        if path not in self.subscribers:
            self.subscribers[path] = set()
        self.subscribers[path].add(queue)
    
    def remove_subscriber(self, path: str, queue: asyncio.Queue) -> None:
        """サブスクライバーを削除"""
        if path in self.subscribers:
            self.subscribers[path].discard(queue)
            if not self.subscribers[path]:
                del self.subscribers[path]
    
    def _notify_subscribers(self, path: str, signal: signal_pb2.Signal) -> None:
        """サブスクライバーに通知"""
        if path in self.subscribers:
            for queue in self.subscribers[path]:
                try:
                    queue.put_nowait(signal)
                except asyncio.QueueFull:
                    logger.warning(f"Queue is full for path: {path}")

class CarlaClient:
    """CARLAシミュレーターとの連携クライアント"""
    
    def __init__(self, signal_store: SignalStore):
        self.signal_store = signal_store
        self._initialize_carla_signals()
    
    def _initialize_carla_signals(self):
        """CARLA関連の信号を初期化"""
        # CARLAの車両信号を追加
        carla_signals = {
            "Vehicle.Speed": self._create_signal("Vehicle.Speed", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 0.0),
            "Vehicle.Engine.RPM": self._create_signal("Vehicle.Engine.RPM", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_UINT32, 0),
            "Vehicle.Battery.Voltage": self._create_signal("Vehicle.Battery.Voltage", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 12.0),
            "Vehicle.Doors.FrontLeft": self._create_signal("Vehicle.Doors.FrontLeft", types_pb2.LEAF_TYPE_ACTUATOR, types_pb2.TYPE_BOOL, False),
            "Vehicle.Lights.Headlights": self._create_signal("Vehicle.Lights.Headlights", types_pb2.LEAF_TYPE_ACTUATOR, types_pb2.TYPE_BOOL, False),
            "Vehicle.Temperature.Engine": self._create_signal("Vehicle.Temperature.Engine", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 85.0),
            "Vehicle.Position.X": self._create_signal("Vehicle.Position.X", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 0.0),
            "Vehicle.Position.Y": self._create_signal("Vehicle.Position.Y", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 0.0),
            "Vehicle.Position.Z": self._create_signal("Vehicle.Position.Z", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 0.0),
            "Vehicle.Orientation.Yaw": self._create_signal("Vehicle.Orientation.Yaw", types_pb2.LEAF_TYPE_SENSOR, types_pb2.TYPE_FLOAT, 0.0),
        }
        
        for path, signal in carla_signals.items():
            self.signal_store.set_signal(path, signal)
    
    def _create_signal(self, path: str, leaf_type: types_pb2.LeafType, data_type: types_pb2.ValueType, default_value) -> signal_pb2.Signal:
        """信号オブジェクトを作成"""
        # Valueオブジェクトを作成
        value = types_pb2.Value()
        if isinstance(default_value, float):
            value.float_value = default_value
        elif isinstance(default_value, int):
            if data_type == types_pb2.TYPE_UINT32:
                value.uint32_value = default_value
            else:
                value.int32_value = default_value
        elif isinstance(default_value, bool):
            value.bool_value = default_value
        
        # Stateオブジェクトを作成
        state = signal_pb2.State()
        state.value.CopyFrom(value)
        state.capability = True
        state.availability = True
        
        # Configオブジェクトを作成
        config = signal_pb2.Config()
        config.leaf_type = leaf_type
        config.data_type = data_type
        config.description = f'CARLA signal for {path}'
        config.end_point = path
        
        # 単位を設定
        if 'Speed' in path:
            config.unit = 'km/h'
        elif 'RPM' in path:
            config.unit = 'RPM'
        elif 'Voltage' in path:
            config.unit = 'V'
        elif 'Temperature' in path:
            config.unit = '°C'
        elif 'Position' in path:
            config.unit = 'm'
        elif 'Orientation' in path:
            config.unit = 'degrees'
        
        # Signalオブジェクトを作成
        signal = signal_pb2.Signal()
        signal.path = path
        signal.state.CopyFrom(state)
        signal.config.CopyFrom(config)
        
        return signal
    
    async def update_vehicle_speed(self, speed: float):
        """車両速度を更新"""
        signal = self.signal_store.get_signal("Vehicle.Speed")
        if signal:
            signal.state.value.float_value = speed
            self.signal_store.set_signal("Vehicle.Speed", signal)
            logger.info(f"Vehicle speed updated: {speed} km/h")
    
    async def update_engine_rpm(self, rpm: int):
        """エンジンRPMを更新"""
        signal = self.signal_store.get_signal("Vehicle.Engine.RPM")
        if signal:
            signal.state.value.uint32_value = rpm
            self.signal_store.set_signal("Vehicle.Engine.RPM", signal)
            logger.info(f"Engine RPM updated: {rpm}")
    
    async def update_vehicle_position(self, x: float, y: float, z: float):
        """車両位置を更新"""
        for coord, value in [("X", x), ("Y", y), ("Z", z)]:
            path = f"Vehicle.Position.{coord}"
            signal = self.signal_store.get_signal(path)
            if signal:
                signal.state.value.float_value = value
                self.signal_store.set_signal(path, signal)
        logger.info(f"Vehicle position updated: ({x}, {y}, {z})")
    
    async def update_vehicle_orientation(self, yaw: float):
        """車両の向きを更新"""
        signal = self.signal_store.get_signal("Vehicle.Orientation.Yaw")
        if signal:
            signal.state.value.float_value = yaw
            self.signal_store.set_signal("Vehicle.Orientation.Yaw", signal)
            logger.info(f"Vehicle orientation updated: {yaw} degrees")
    
    async def toggle_headlights(self, on: bool):
        """ヘッドライトの切り替え"""
        signal = self.signal_store.get_signal("Vehicle.Lights.Headlights")
        if signal:
            signal.state.value.bool_value = on
            self.signal_store.set_signal("Vehicle.Lights.Headlights", signal)
            status = "ON" if on else "OFF"
            logger.info(f"Headlights {status}")
    
    async def toggle_door(self, door_path: str, open: bool):
        """ドアの開閉"""
        signal = self.signal_store.get_signal(door_path)
        if signal:
            signal.state.value.bool_value = open
            self.signal_store.set_signal(door_path, signal)
            status = "opened" if open else "closed"
            logger.info(f"Door {door_path} {status}")
    
    def get_all_signals(self) -> Dict[str, signal_pb2.Signal]:
        """すべての信号を取得"""
        return self.signal_store.signals.copy()
    
    def get_signal_value(self, path: str):
        """指定された信号の値を取得"""
        signal = self.signal_store.get_signal(path)
        if signal and signal.state.value:
            # 値の型に応じて適切な値を返す
            if signal.state.value.HasField('float_value'):
                return signal.state.value.float_value
            elif signal.state.value.HasField('uint32_value'):
                return signal.state.value.uint32_value
            elif signal.state.value.HasField('bool_value'):
                return signal.state.value.bool_value
            elif signal.state.value.HasField('string_value'):
                return signal.state.value.string_value
        return None