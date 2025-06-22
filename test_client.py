#!/usr/bin/env python3
"""
SignalServiceのテスト用クライアント
"""

import asyncio
import logging
from typing import List

# 生成されたプロトコルバッファファイルをインポート
try:
    import sys
    sys.path.append('generated')
    from vehicle_shadow import signal_pb2, signal_pb2_grpc, types_pb2
except ImportError:
    print("警告: 生成されたプロトコルバッファファイルが見つかりません")
    print("python generate_proto.py を実行してファイルを生成してください")
    import sys
    sys.exit(1)

import grpc

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SignalServiceClient:
    """SignalServiceのクライアント"""
    
    def __init__(self, host: str = 'localhost', port: int = 50051):
        self.channel = grpc.aio.insecure_channel(f'{host}:{port}')
        self.stub = signal_pb2_grpc.SignalServiceStub(self.channel)
    
    async def close(self):
        """チャンネルを閉じる"""
        await self.channel.close()
    
    async def get_signals(self, paths: List[str]) -> signal_pb2.GetResponse:
        """信号を取得"""
        request = signal_pb2.GetRequest()
        request.paths.extend(paths)
        
        response = await self.stub.Get(request)
        return response
    
    async def set_signals(self, signals: List[dict], token: str = "") -> signal_pb2.SetResponse:
        """信号を設定"""
        request = signal_pb2.SetRequest()
        request.token = token
        
        for signal_data in signals:
            signal_request = signal_pb2.SetSignalRequest()
            signal_request.path = signal_data['path']
            signal_request.state.CopyFrom(signal_data['state'])
            request.signals.append(signal_request)
        
        response = await self.stub.Set(request)
        return response
    
    async def lock_signals(self, paths: List[str]) -> signal_pb2.LockResponse:
        """信号をロック"""
        request = signal_pb2.LockRequest()
        request.paths.extend(paths)
        
        response = await self.stub.Lock(request)
        return response
    
    async def unlock_signals(self, token: str) -> signal_pb2.UnlockResponse:
        """信号のロックを解除"""
        request = signal_pb2.UnlockRequest()
        request.token = token
        
        response = await self.stub.Unlock(request)
        return response
    
    async def subscribe_to_signals(self, paths: List[str]):
        """信号の変更をサブスクライブ"""
        request = signal_pb2.SubscribeRequest()
        request.paths.extend(paths)
        
        async for response in self.stub.Subscribe(request):
            yield response

def create_value(value, value_type: types_pb2.ValueType):
    """Valueオブジェクトを作成"""
    val = types_pb2.Value()
    
    if value_type == types_pb2.TYPE_BOOL:
        val.bool_value = value
    elif value_type == types_pb2.TYPE_FLOAT:
        val.float_value = value
    elif value_type == types_pb2.TYPE_UINT32:
        val.uint32_value = value
    elif value_type == types_pb2.TYPE_STRING:
        val.string_value = value
    else:
        val.int32_value = value
    
    return val

def create_state(value=None, capability: bool = True, availability: bool = True):
    """Stateオブジェクトを作成"""
    state = signal_pb2.State()
    if value is not None:
        state.value.CopyFrom(value)
    state.capability = capability
    state.availability = availability
    return state

async def test_get_signals(client: SignalServiceClient):
    """信号取得のテスト"""
    print("\n=== 信号取得テスト ===")
    
    # CARLA信号を取得
    paths = [
        "Vehicle.Speed", 
        "Vehicle.Engine.RPM", 
        "Vehicle.Battery.Voltage",
        "Vehicle.Position.X",
        "Vehicle.Position.Y",
        "Vehicle.Position.Z",
        "Vehicle.Orientation.Yaw"
    ]
    response = await client.get_signals(paths)
    
    if response.success:
        print(f"成功: {len(response.signals)}個の信号を取得")
        for signal in response.signals:
            value_str = "N/A"
            if signal.state.value:
                if signal.state.value.HasField('float_value'):
                    value_str = f"{signal.state.value.float_value}"
                elif signal.state.value.HasField('uint32_value'):
                    value_str = f"{signal.state.value.uint32_value}"
                elif signal.state.value.HasField('bool_value'):
                    value_str = f"{signal.state.value.bool_value}"
            print(f"  - {signal.path}: {value_str} {signal.config.unit or ''}")
    else:
        print(f"エラー: {response.error_message}")

async def test_set_signals(client: SignalServiceClient):
    """信号設定のテスト"""
    print("\n=== 信号設定テスト ===")
    
    # 新しい値を設定
    signals = [
        {
            'path': 'Vehicle.Speed',
            'state': create_state(create_value(60.5, types_pb2.TYPE_FLOAT))
        },
        {
            'path': 'Vehicle.Engine.RPM',
            'state': create_state(create_value(2500, types_pb2.TYPE_UINT32))
        },
        {
            'path': 'Vehicle.Position.X',
            'state': create_state(create_value(100.0, types_pb2.TYPE_FLOAT))
        },
        {
            'path': 'Vehicle.Position.Y',
            'state': create_state(create_value(200.0, types_pb2.TYPE_FLOAT))
        }
    ]
    
    response = await client.set_signals(signals)
    
    if response.success:
        print("成功: 信号を設定")
        for result in response.results:
            status = "成功" if result.success else "失敗"
            print(f"  - {result.path}: {status}")
            if not result.success:
                print(f"    エラー: {result.error_message}")
    else:
        print(f"エラー: {response.error_message}")

async def test_lock_unlock(client: SignalServiceClient):
    """ロック/アンロックのテスト"""
    print("\n=== ロック/アンロックテスト ===")
    
    # 信号をロック
    paths = ["Vehicle.Speed", "Vehicle.Engine.RPM"]
    lock_response = await client.lock_signals(paths)
    
    if lock_response.success:
        print(f"成功: 信号をロック (トークン: {lock_response.token})")
        
        # ロックされた信号を設定してみる（失敗するはず）
        signals = [
            {
                'path': 'Vehicle.Speed',
                'state': create_state(create_value(100.0, types_pb2.TYPE_FLOAT))
            }
        ]
        
        set_response = await client.set_signals(signals)
        print("ロックされた信号の設定試行:")
        for result in set_response.results:
            status = "成功" if result.success else "失敗"
            print(f"  - {result.path}: {status}")
            if not result.success:
                print(f"    エラー: {result.error_message}")
        
        # 正しいトークンで設定してみる
        set_response_with_token = await client.set_signals(signals, lock_response.token)
        print("正しいトークンでの設定試行:")
        for result in set_response_with_token.results:
            status = "成功" if result.success else "失敗"
            print(f"  - {result.path}: {status}")
        
        # ロックを解除
        unlock_response = await client.unlock_signals(lock_response.token)
        if unlock_response.success:
            print("成功: 信号のロックを解除")
        else:
            print("失敗: 信号のロック解除")
    else:
        print("失敗: 信号のロック")

async def test_subscription(client: SignalServiceClient):
    """サブスクリプションのテスト"""
    print("\n=== サブスクリプションテスト ===")
    
    paths = ["Vehicle.Speed", "Vehicle.Position.X"]
    
    # 別のタスクで信号を変更
    async def change_signals():
        await asyncio.sleep(2)
        signals = [
            {
                'path': 'Vehicle.Speed',
                'state': create_state(create_value(80.0, types_pb2.TYPE_FLOAT))
            },
            {
                'path': 'Vehicle.Position.X',
                'state': create_state(create_value(150.0, types_pb2.TYPE_FLOAT))
            }
        ]
        await client.set_signals(signals)
        print("信号を変更しました")
    
    # サブスクリプションを開始
    subscription_task = asyncio.create_task(change_signals())
    
    try:
        count = 0
        async for response in client.subscribe_to_signals(paths):
            if response.signal:
                value_str = "N/A"
                if response.signal.state.value:
                    if response.signal.state.value.HasField('float_value'):
                        value_str = f"{response.signal.state.value.float_value}"
                    elif response.signal.state.value.HasField('uint32_value'):
                        value_str = f"{response.signal.state.value.uint32_value}"
                    elif response.signal.state.value.HasField('bool_value'):
                        value_str = f"{response.signal.state.value.bool_value}"
                print(f"信号変更を受信: {response.signal.path} = {value_str}")
                count += 1
                if count >= 2:  # 2回受信したら終了
                    break
            elif response.error_message:
                print(f"サブスクリプションエラー: {response.error_message}")
                break
    except Exception as e:
        print(f"サブスクリプションエラー: {e}")
    finally:
        await subscription_task

async def test_carla_specific_signals(client: SignalServiceClient):
    """CARLA固有の信号テスト"""
    print("\n=== CARLA固有信号テスト ===")
    
    # 車両の位置と向きを設定
    signals = [
        {
            'path': 'Vehicle.Position.X',
            'state': create_state(create_value(500.0, types_pb2.TYPE_FLOAT))
        },
        {
            'path': 'Vehicle.Position.Y',
            'state': create_state(create_value(300.0, types_pb2.TYPE_FLOAT))
        },
        {
            'path': 'Vehicle.Position.Z',
            'state': create_state(create_value(0.5, types_pb2.TYPE_FLOAT))
        },
        {
            'path': 'Vehicle.Orientation.Yaw',
            'state': create_state(create_value(45.0, types_pb2.TYPE_FLOAT))
        },
        {
            'path': 'Vehicle.Lights.Headlights',
            'state': create_state(create_value(True, types_pb2.TYPE_BOOL))
        }
    ]
    
    response = await client.set_signals(signals)
    
    if response.success:
        print("成功: CARLA信号を設定")
        for result in response.results:
            status = "成功" if result.success else "失敗"
            print(f"  - {result.path}: {status}")
    else:
        print(f"エラー: {response.error_message}")
    
    # 設定した信号を取得して確認
    paths = [signal['path'] for signal in signals]
    get_response = await client.get_signals(paths)
    
    if get_response.success:
        print("設定された信号の確認:")
        for signal in get_response.signals:
            value_str = "N/A"
            if signal.state.value:
                if signal.state.value.HasField('float_value'):
                    value_str = f"{signal.state.value.float_value}"
                elif signal.state.value.HasField('bool_value'):
                    value_str = f"{signal.state.value.bool_value}"
            print(f"  - {signal.path}: {value_str} {signal.config.unit or ''}")

async def main():
    """メイン関数"""
    client = SignalServiceClient()
    
    try:
        # 各テストを実行
        await test_get_signals(client)
        await test_set_signals(client)
        await test_lock_unlock(client)
        await test_subscription(client)
        await test_carla_specific_signals(client)
        
    except Exception as e:
        print(f"エラー: {e}")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main()) 