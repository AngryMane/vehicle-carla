import asyncio
import uuid
import logging
from typing import Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor
import grpc
from grpc import aio

# carla_clientから必要なクラスをインポート
try:
    from carla_client import SignalStore, CarlaClient
except ImportError as e:
    print(f"警告: carla_clientモジュールが見つかりません: {e}")
    SignalStore = None
    CarlaClient = None

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

class SignalServiceServicer(signal_pb2_grpc.SignalServiceServicer):
    """SignalServiceのサーバー実装"""
    
    def __init__(self):
        if not SignalStore or not CarlaClient:
            raise ImportError("必要なモジュールがインポートできませんでした")
        
        self.signal_store = SignalStore()
        self.carla_client = CarlaClient(self.signal_store)
        logger.info("SignalService initialized with CARLA client")
    
    async def Get(self, request: signal_pb2.GetRequest, context) -> signal_pb2.GetResponse:
        """複数の信号を取得"""
        try:
            signals = []
            for path in request.paths:
                signal = self.signal_store.get_signal(path)
                if signal:
                    signals.append(signal)
                else:
                    logger.warning(f"Signal not found: {path}")
            
            response = signal_pb2.GetResponse()
            response.signals.extend(signals)
            response.success = True
            
            return response
        except Exception as e:
            logger.error(f"Error in Get: {e}")
            response = signal_pb2.GetResponse()
            response.success = False
            response.error_message = str(e)
            return response
    
    async def Set(self, request: signal_pb2.SetRequest, context) -> signal_pb2.SetResponse:
        """複数の信号値を設定"""
        try:
            results = []
            token = request.token
            
            for signal_request in request.signals:
                path = signal_request.path
                state = signal_request.state
                
                # ロックチェック
                if self.signal_store.is_locked(path):
                    if not token or self.signal_store.locks.get(path) != token:
                        result = signal_pb2.SetResult()
                        result.path = path
                        result.success = False
                        result.error_message = 'Signal is locked by another client'
                        results.append(result)
                        continue
                
                # 信号を更新
                current_signal = self.signal_store.get_signal(path)
                if current_signal:
                    current_signal.state.CopyFrom(state)
                    self.signal_store.set_signal(path, current_signal)
                    
                    result = signal_pb2.SetResult()
                    result.path = path
                    result.success = True
                    results.append(result)
                else:
                    result = signal_pb2.SetResult()
                    result.path = path
                    result.success = False
                    result.error_message = 'Signal not found'
                    results.append(result)
            
            response = signal_pb2.SetResponse()
            response.results.extend(results)
            response.success = True
            
            return response
        except Exception as e:
            logger.error(f"Error in Set: {e}")
            response = signal_pb2.SetResponse()
            response.success = False
            response.error_message = str(e)
            return response
    
    async def Subscribe(self, request: signal_pb2.SubscribeRequest, context):
        """信号の変更をサブスクライブ"""
        try:
            # 各パスに対してサブスクライブ
            queues = []
            for path in request.paths:
                queue = asyncio.Queue()
                self.signal_store.add_subscriber(path, queue)
                queues.append((path, queue))
            
            try:
                while context.is_active():
                    # 各キューからメッセージを待機
                    done, pending = await asyncio.wait(
                        [asyncio.create_task(queue.get()) for _, queue in queues],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    for task in done:
                        try:
                            signal = task.result()
                            response = signal_pb2.SubscribeResponse()
                            response.signal.CopyFrom(signal)
                            yield response
                        except Exception as e:
                            logger.error(f"Error processing subscription: {e}")
                            response = signal_pb2.SubscribeResponse()
                            response.error_message = str(e)
                            yield response
                    
                    # 完了したタスクを再作成
                    for task in pending:
                        task.cancel()
                        
            finally:
                # クリーンアップ
                for path, queue in queues:
                    self.signal_store.remove_subscriber(path, queue)
                    
        except Exception as e:
            logger.error(f"Error in Subscribe: {e}")
            response = signal_pb2.SubscribeResponse()
            response.error_message = str(e)
            yield response
    
    async def Unsubscribe(self, request: signal_pb2.UnsubscribeRequest, context) -> signal_pb2.UnsubscribeResponse:
        """信号の変更のサブスクライブを解除"""
        try:
            # 注: 実際の実装では、特定のサブスクライバーを識別する必要がある
            # ここでは簡略化のため、成功を返す
            response = signal_pb2.UnsubscribeResponse()
            response.success = True
            return response
        except Exception as e:
            logger.error(f"Error in Unsubscribe: {e}")
            response = signal_pb2.UnsubscribeResponse()
            response.success = False
            response.error_message = str(e)
            return response
    
    async def Lock(self, request: signal_pb2.LockRequest, context) -> signal_pb2.LockResponse:
        """信号をロック"""
        try:
            token = str(uuid.uuid4())
            locked_paths = []
            
            for path in request.paths:
                if self.signal_store.lock_signal(path, token):
                    locked_paths.append(path)
                else:
                    logger.warning(f"Failed to lock signal: {path}")
            
            success = len(locked_paths) == len(request.paths)
            
            response = signal_pb2.LockResponse()
            response.success = success
            response.token = token if success else ''
            
            return response
        except Exception as e:
            logger.error(f"Error in Lock: {e}")
            response = signal_pb2.LockResponse()
            response.success = False
            response.token = ''
            return response
    
    async def Unlock(self, request: signal_pb2.UnlockRequest, context) -> signal_pb2.UnlockResponse:
        """信号のロックを解除"""
        try:
            token = request.token
            unlocked_count = 0
            
            # トークンに関連するすべてのロックを解除
            paths_to_unlock = [path for path, lock_token in self.signal_store.locks.items() 
                             if lock_token == token]
            
            for path in paths_to_unlock:
                if self.signal_store.unlock_signal(path, token):
                    unlocked_count += 1
            
            success = unlocked_count > 0
            
            response = signal_pb2.UnlockResponse()
            response.success = success
            
            return response
        except Exception as e:
            logger.error(f"Error in Unlock: {e}")
            response = signal_pb2.UnlockResponse()
            response.success = False
            return response

async def serve():
    """gRPCサーバーを起動"""
    if not signal_pb2_grpc:
        print("エラー: プロトコルバッファファイルが生成されていません")
        print("python generate_proto.py を実行してください")
        return
    
    server = aio.server()
    
    # サーバーにサービスを追加
    signal_pb2_grpc.add_SignalServiceServicer_to_server(
        SignalServiceServicer(), server
    )
    
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting SignalService server on {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        await server.stop(0)

if __name__ == '__main__':
    asyncio.run(serve()) 