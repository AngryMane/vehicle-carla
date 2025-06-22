import asyncio
import uuid
import logging
from typing import Dict, List, Optional, Set
import grpc
from grpc import aio
import carla
import time
import math


# プロトコルバッファの生成されたコードをインポート
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

class CarlaClient:
    """CARLAシミュレーターとの連携クライアント"""
    
    def __init__(self):
        client = carla.Client('localhost', 2000)
        client.set_timeout(10.0)
        world = client.get_world()
        blueprint_library = world.get_blueprint_library()
        vehicle_bp = blueprint_library.filter('vehicle.*model3*')[0]
        self.spawn_point = world.get_map().get_spawn_points()[1]
        self.vehicle = world.spawn_actor(vehicle_bp, self.spawn_point)
        self.vehicle.set_autopilot(False)
        self.spectator = world.get_spectator()
        forward_vector = self.spawn_point.get_forward_vector()
        speed = 0
        velocity = carla.Vector3D(
            x=forward_vector.x * speed,
            y=forward_vector.y * speed,
            z=0
        )
        self.vehicle.set_target_velocity(velocity)

        transform = self.vehicle.get_transform()

        # 追従視点の位置を車両の後方 & 上に設定（例: 8m後ろ・3m上）
        offset = transform.get_forward_vector() * -8.0  # 後ろへ
        offset.z += 3.0  # 上へ

        spectator_transform = carla.Transform(
            transform.location + offset,
            transform.rotation
        )

        self.spectator.set_transform(spectator_transform)
    
    async def update_vehicle_speed(self, speed: float):
        """車両速度を更新"""
        forward_vector = self.spawn_point.get_forward_vector()
        velocity = carla.Vector3D(
            x=forward_vector.x * speed,
            y=forward_vector.y * speed,
            z=0
        )
        self.vehicle.set_target_velocity(velocity)
        signal = self.signal_store.get_signal("Vehicle.Speed")
        if signal:
            signal.state.value.float_value = speed
            self.signal_store.set_signal("Vehicle.Speed", signal)
            logger.info(f"Vehicle speed updated: {speed} km/h")
    
    async def toggle_headlights(self, on: bool):
        """ヘッドライトの切り替え"""
        pass
    
    async def toggle_door(self, door_path: str, open: bool):
        """ドアの開閉"""
        pass
    
    def get_all_signals(self) -> Dict[str, signal_pb2.Signal]:
        """すべての信号を取得"""
        pass
    